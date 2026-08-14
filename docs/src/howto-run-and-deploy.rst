Run and deploy the Namespace Manager
====================================

This page covers running the components on your own machine, building the
image, deploying the Helm chart, supplying secrets from Vault, and the
day-to-day changes operators make. Every configuration key mentioned here is
described in :doc:`reference-configuration`.

Set up a working copy
---------------------

The repository uses the shared SKAO tooling submodule, and ``uv`` for
dependencies:

.. code-block:: bash

   git clone git@gitlab.com:ska-telescope/ska-ser-namespace-manager.git
   cd ska-ser-namespace-manager
   git submodule update --init --recursive
   uv sync

Formatting, linting and tests go through the repository ``Makefile``, which
already runs everything inside the ``uv`` environment:

.. code-block:: bash

   make python-format
   make python-lint
   make python-test     # unit tests, ./tests/unit

The integration suite under ``tests/integration`` needs a cluster and is run by
CI through ``make k8s-test``; it skips itself unless ``NSTEST_MANAGER_NAMESPACE``
or ``KUBE_NAMESPACE`` is set.

To build this documentation:

.. code-block:: bash

   make docs-build html   # output in docs/build/html

Run a component on your machine
-------------------------------

Each component reads one YAML file or one directory of YAML files, chosen with
``CONFIG_PATH``. Nothing else is required — no database, and no external
binaries.

**The API needs no cluster access at all**, which makes it the easiest
component to run locally:

.. code-block:: bash

   mkdir -p /tmp/nsm/metrics
   cat > /tmp/nsm/00-base.yml <<'YAML'
   metrics:
     enabled: true
     registry_path: /tmp/nsm/metrics
   YAML

   CONFIG_PATH=/tmp/nsm uv run python3 src/api.py

With ``https_enabled`` left at its default the API serves plain HTTP on port
8080, the People Database is disabled (so ``/health/readiness`` is immediately
ready and ``/api/people`` answers ``not found``), and ``/api/metrics`` returns
whatever ``*.prom`` files exist in ``registry_path``.

The controllers need a cluster. Outside one, pass ``--kubeconfig`` — without it
they try the in-cluster configuration and exit:

.. code-block:: bash

   cat > /tmp/nsm-collect/00-base.yml <<'YAML'
   context:
     namespace: ska-ser-namespace-manager
     service_account: local
     image: local
     config_path: /tmp/nsm-collect
     config_secret: none
   leader_election:
     enabled: false
   metrics:
     registry_path: /tmp/nsm-collect/metrics
   prometheus:
     enabled: false
   namespaces:
     - names:
         - ci-.*
       ttl: 5m
       actions:
         check-namespace:
           schedule: 30s
   YAML

   CONFIG_PATH=/tmp/nsm-collect uv run python3 src/collect_controller.py \
     --kubeconfig ~/.kube/config

``context`` and ``leader_election`` are required for both controllers, and the
action controller additionally requires a ``namespaces`` list — the chart
normally renders all of these, so a hand-written local file has to supply them.

.. note::

   A collect controller running **outside** the cluster adopts matching
   namespaces and marks them managed, but does not health-check them. Each
   replica only checks the namespaces that hash to its own pod name, and a
   process whose hostname is not in the discovered replica list is assigned
   nothing (it logs ``Skipping namespace checks because current pod … was not
   found in the discovered replica set``). Use an in-cluster deployment, or the
   integration tests, to exercise the check loop.

Set ``LOG_LEVEL=DEBUG`` for verbose output. An unrecognised level raises at
import time, so a typo stops the process before any other message appears.

Build and run the image
-----------------------

.. code-block:: bash

   make oci-build-all CAR_OCI_REGISTRY_HOST=localhost:5000

The image's entrypoint is ``python3 -u`` and its default command is the API
script, so the component is chosen by the argument:

.. code-block:: bash

   docker run --rm -p 8080:8080 \
     -e CONFIG_PATH=/etc/config \
     -v /tmp/nsm:/etc/config:ro \
     -v /tmp/nsm/metrics:/etc/metrics \
     <image> /opt/ska_ser_namespace_manager/api.py

Replace the final argument with ``collect_controller.py`` or
``action_controller.py`` for the controllers, and add ``--kubeconfig`` after it
if the container is not running inside the cluster.

Deploy with Helm
----------------

The chart lives in ``charts/ska-ser-namespace-manager`` and is installed
through the shared make targets. Values files in
``charts/ska-ser-namespace-manager/environments/`` are selected with
``ENVIRONMENT`` and passed through ``envsubst``, so they may reference
environment variables; ``all.yml`` is always applied when present.

.. code-block:: bash

   make k8s-template-chart ENVIRONMENT=local   # render without installing
   make k8s-install-chart  ENVIRONMENT=local
   make k8s-uninstall-chart

Extra values files can be layered on top with ``K8S_EXTRA_VALUES`` (later files
win):

.. code-block:: bash

   make k8s-install-chart ENVIRONMENT=local K8S_EXTRA_VALUES="./my-values.yml"

For a local cluster such as the
`SDI CI/CD minikube cluster <https://gitlab.com/ska-telescope/sdi/ska-cicd-deploy-minikube>`_,
build the image into the local registry first and point ``image.repository`` at
``<local ip>:5000``.

.. warning::

   The shipped defaults do not produce a working API. ``values.yaml`` sets
   ``api.config.people_database.enabled: true`` with an empty credentials
   skeleton, and the rendered configuration then fails validation — the API pod
   crash-loops with six missing-credential errors. Either layer real
   credentials in (as ``environments/ci.yml`` does, see
   `Supply secrets from Vault instead of values`_) or set
   ``api.config.people_database.enabled: false``.

   Two storage defaults also need attention on a fresh cluster. Both the
   metrics claim and the collect controller's leader-election claim are
   ``ReadWriteMany``, and the leader-election claim is created by default
   (``collectController.replicas: 3``) with no storage class, so it will stay
   ``Pending`` unless you set
   ``collectController.pvc.leaderElection.storageClassName`` to a class that
   supports RWX and ``flock``.

The chart creates, per component, a Deployment or StatefulSet, a config Secret
holding ``00-base.yml``, RBAC, and — when it needs them — Services and
PersistentVolumeClaims. Both controllers get a ClusterRole allowing them to
read and patch namespaces cluster-wide; only the action controller may delete
them. The API gets no ServiceAccount and no RBAC, because it never calls the
Kubernetes API.

Chart values you will actually set
----------------------------------

Values are grouped by component: ``api``, ``collectController`` and
``actionController`` each accept the same deployment-shaped keys, while
``<component>.config`` is the application configuration documented in
:doc:`reference-configuration`.

Identity and image
~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 25 40

   * - Value
     - Default
     - Purpose
   * - ``image.repository``
     - ``artefact.skao.int/ska-ser-namespace-manager``
     - Image for all three components.
   * - ``image.tag``
     - chart ``appVersion``
     - Overridden per component with ``<component>.image.tag``.
   * - ``image.pullPolicy``
     - ``IfNotPresent``
     - Applies to all three components. Unlike ``repository`` and ``tag``, the
       per-component ``<component>.image.pullPolicy`` is **not** honoured — the
       global value always wins.
   * - ``nameOverride`` / ``fullnameOverride``
     - unset
     - Rename the release's resources.
   * - ``labels``
     - ``{}``
     - Extra labels on every resource; ``<component>.labels`` and
       ``<component>.annotations`` add pod-level metadata.
   * - ``configPath``
     - ``/etc/config``
     - Mount point for the config Secret and the value of ``CONFIG_PATH``.
   * - ``clusterWide.usePrefix``
     - ``true``
     - Prefixes ClusterRole and ClusterRoleBinding names with a hash of the
       release namespace, so several releases can coexist in one cluster.

Replicas, leader election and storage
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 40 20 40

   * - Value
     - Default
     - Purpose
   * - ``api.replicas``
     - ``1``
     - Stateless; scale freely.
   * - ``collectController.replicas``
     - ``3``
     - Namespaces are shared out across replicas by hash.
   * - ``actionController.replicas``
     - ``1``
     - See the warning below before increasing this.
   * - ``<component>.pvc.leaderElection.storageClassName``
     - unset
     - Storage class for the leader-election volume. A ``ReadWriteMany`` 1 Mi
       claim is created **only when that component has more than one replica**,
       and the class must support ``flock``.
   * - ``config.metrics.pvc.storageClassName``
     - ``nfss1``
     - Storage class for the shared metrics volume.
   * - ``config.metrics.pvc.size``
     - ``1Gi``
     - Size of that claim. It is ``ReadWriteMany`` and mounted by all three
       components; it is created only while ``config.metrics.enabled`` is true.
   * - ``collectController.podManagementPolicy``
     - ``OrderedReady``
     - StatefulSet pod management.
   * - ``<component>.updateStrategy``
     - ``RollingUpdate`` (``maxSurge: 1``, ``maxUnavailable: 40%`` for the two
       Deployments)
     - Passed through verbatim.

.. warning::

   Leader election is enabled by the chart **only when a component runs more
   than one replica**, and the value in ``<component>.config.leader_election``
   is overridden accordingly. Two caveats apply if you scale the action
   controller past one replica: its delete and notify loops are not
   leader-gated, so every replica acts, and its leader-election volume is
   mounted read-only, which prevents the lock from being taken. Keep
   ``actionController.replicas: 1`` unless both have been addressed.

Resources, scheduling and probes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 40 25 35

   * - Value
     - Default
     - Purpose
   * - ``api.resources``
     - requests ``100m`` / ``128Mi``, limit ``512Mi``
     - No CPU limit is set.
   * - ``collectController.resources`` / ``actionController.resources``
     - requests ``400m`` / ``512Mi``, limit ``2Gi``
     - The collect controller runs one thread per assigned namespace, so memory
       scales with the number of managed namespaces.
   * - ``<component>.nodeSelector`` / ``.tolerations``
     - ``{}`` / ``[]``
     - Fall back to the top-level ``nodeSelector`` and ``tolerations`` when
       empty.
   * - ``<component>.antiAffinity.enabled``
     - ``true``
     - Applies the component's ``podAntiAffinity``, which prefers spreading
       replicas across hosts. ``podAffinity``, ``nodeAffinity`` and
       ``topologySpreadConstraints`` are passed through as written.
   * - ``<component>.priorityClassName``
     - ``""``
     - Pod priority class.
   * - ``<component>.apiPriorityAndFairness``
     - ``false``
     - Creates a ``PriorityLevelConfiguration`` from
       ``priorityLevelConfigurationSpec`` for that component's traffic to the
       API server. Leave it off: the template emits ``apiVersion: v1`` rather
       than ``flowcontrol.apiserver.k8s.io/v1``, so the API server rejects the
       manifest, and no matching ``FlowSchema`` is created either.
   * - ``<component>.podSecurityContext`` / ``.securityContext``
     - ``{}``
     - Pod- and container-level security context.
   * - ``api.startupProbe`` / ``.livenessProbe`` / ``.readinessProbe``
     - HTTPS on ``9443``
     - **Hardcoded to HTTPS and 9443.** If you set
       ``api.service.https.enabled: false``, override the three probes to use
       ``HTTP`` on ``8080`` as well.
   * - ``collectController.livenessProbe``
     - ``exec`` on the heartbeat file
     - Fails when the heartbeat file is older than
       ``collectController.config.heartbeat.max_age_seconds``.
   * - ``actionController.*Probe``
     - empty
     - The action controller has no probes.

Services and TLS
~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 40 22 38

   * - Value
     - Default
     - Purpose
   * - ``api.service.https.enabled``
     - ``true``
     - Serves TLS on ``https_port``; also sets ``https_enabled`` in the
       rendered config and selects the Service port. When false the API serves
       plain HTTP and the Service exposes port ``80``.
   * - ``api.service.https.port`` / ``http.port``
     - ``443`` / ``80``
     - Service ports.
   * - ``api.service.https.type``
     - ``LoadBalancer``
     - Service type **in both modes** — ``api.service.http.type`` is never
       read, so set ``https.type`` even when serving plain HTTP. ``nodePort``
       is honoured only when the matching ``type`` is ``NodePort``, and only
       ``https.annotations`` reach the Service.
   * - ``api.pki.createSelfSignedCert``
     - ``true``
     - Generates a CA and serving certificate into ``<api-svc>-cert``.
       Set ``false`` **and** supply all three of ``api.pki.ca``, ``.cert`` and
       ``.key``; setting it to ``false`` on its own fails the render with
       ``<b64enc>: invalid value; expected string``.

The collect controller also gets a headless Service, used only for stable
StatefulSet DNS — no component listens on it.

Escape hatches
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Value
     - Purpose
   * - ``extraDeploy``
     - Arbitrary manifests rendered with the release. Each entry is passed
       through ``tpl``, so chart helpers such as
       ``{{ template "ska-ser-namespace-manager.namespace" . }}`` work. This is
       where ``VaultStaticSecret`` resources are declared.
   * - ``<component>.extraConfigSecrets``
     - Additional Secrets projected into ``configPath`` alongside
       ``00-base.yml``. Each entry takes ``name`` (templated), optional
       ``optional``, and optional ``items`` of ``key``/``path`` pairs.
   * - ``extraEnvVars`` and ``<component>.extraEnvVars``
     - Environment variables; the global list is concatenated before the
       component's.
   * - ``<component>.extraArgs``
     - Extra arguments appended after the entrypoint script — the only way to
       pass ``--kubeconfig`` in a deployment.
   * - ``<component>.imagePullSecrets``
     - Image pull secrets.
   * - ``<component>.dnsPolicy``
     - Pod DNS policy, ``ClusterFirst`` by default.

The chart deliberately stops there. There is no ``extraVolumes`` /
``extraVolumeMounts``, no ``sidecars`` or ``initContainers``, no
``serviceAccount.create`` or ``rbac.create`` switch, and no way to reuse an
existing ``PersistentVolumeClaim`` — the four volumes (config, PKI,
leader election, metrics) are fixed, and claims are always created by the
chart. ``<component>.labels`` and ``<component>.annotations`` reach the pod
template only; the top-level ``labels`` is the only way to label the Deployment
or StatefulSet object itself. Anything else has to go through ``extraDeploy``.

Supply secrets from Vault instead of values
-------------------------------------------

Sensitive fields — the GitLab token, the Slack token, the People Database
private key — should never live in a values file. Because every YAML file in
``configPath`` is merged alphabetically and later files win, a Vault-managed
Secret can override individual keys of the chart's ``00-base.yml``.

Declare the ``VaultStaticSecret`` through ``extraDeploy`` and project it with
``<component>.extraConfigSecrets``:

.. code-block:: yaml

   extraDeploy:
     - apiVersion: secrets.hashicorp.com/v1beta1
       kind: VaultStaticSecret
       metadata:
         name: '{{ template "ska-ser-namespace-manager.name" . }}-config-secrets'
         namespace: '{{ template "ska-ser-namespace-manager.namespace" . }}'
       spec:
         mount: stfc-techops
         type: kv-v2
         path: staging/ci/ska-ser-namespace-manager
         refreshAfter: 60s
         # Configuration is read once at startup, so the workload must be
         # restarted when the secret rotates.
         rolloutRestartTargets:
           - kind: StatefulSet
             name: '{{ template "ska-ser-namespace-manager.collect-controller.name" . }}'
         destination:
           create: true
           name: '{{ template "ska-ser-namespace-manager.name" . }}-config-secrets'
           transformation:
             excludeRaw: true

   collectController:
     extraConfigSecrets:
       - name: '{{ template "ska-ser-namespace-manager.name" . }}-config-secrets'
         items:
           # The Vault key becomes a file in configPath. Any name sorting after
           # 00-base.yml wins on conflicts.
           - key: collect-controller.yml
             path: 99-credentials.yml

The Vault payload's ``collect-controller.yml`` key holds a YAML fragment shaped
like the live configuration:

.. code-block:: yaml

   gitlab:
     private_token: <token>

The same pattern applies to ``api.extraConfigSecrets`` and
``actionController.extraConfigSecrets``. ``charts/ska-ser-namespace-manager/environments/ci.yml``
is a working example for all three components.

.. warning::

   Configuration is read once, at startup. Rotating a projected Secret updates
   the file in the pod but not the running process, which is why
   ``rolloutRestartTargets`` matters. ``helm upgrade`` handles the values-based
   path itself: the rendered configuration is hashed into a
   ``skao.int/configVersion`` pod annotation, so a changed configuration rolls
   the pods.

Common changes
--------------

**Manage a different set of namespaces.** Add or edit entries under
``collectController.config.namespaces`` and
``actionController.config.namespaces``. Both lists are independent: the collect
controller decides status, the action controller decides what to do about it,
and a namespace missing from either list is only half-managed. Matchers accept
``names`` (full-match regular expressions), ``any`` and ``all``.

**Change how long namespaces live.** ``ttl`` on the matching collect entry.
Remember durations need a unit — ``5m``, not ``300``.

**Delete namespaces from cancelled pipelines.** Enable the check and give the
controller a GitLab token:

.. code-block:: yaml

   collectController:
     config:
       gitlab:
         enabled: true
         api_base: https://gitlab.com
         # private_token comes from Vault
       namespaces:
         - names: ["ci-.*"]
           ttl: 5m
           checks:
             cancelled: true
             superseded: true

Enabling ``gitlab`` without a token makes the collect controller fail at
startup, by design.

**Turn Slack notifications on.** Set ``actionController.config.notifier.token``
(from Vault) and ``notify_on_status`` / ``notify_on_delete`` on the statuses you
care about. Without a token the controller logs that notifications are disabled
and keeps running. Owners are resolved from the namespace's
``cicd.skao.int/notificationAddress`` annotation; namespaces without one are
acted on silently.

**Run without the People Database.** Set
``api.config.people_database.enabled: false`` and omit ``spreadsheet_id`` and
``credentials``. The API still starts and passes readiness, and
``/api/people`` answers ``not found``.

**Switch off Prometheus-based health checks.** Set
``collectController.config.prometheus.enabled: false`` and the collector falls
back to comparing available and desired replicas of Deployments, StatefulSets
and ReplicaSets. To keep Prometheus but ignore noisy alerts, list them under
``whitelisted_alerts`` — they then only count when their severity is
``critical``.

.. warning::

   ``values.yaml`` ships ``whitelisted_alerts`` with an explicit empty value,
   which reaches the process as ``null`` rather than an empty list. Health
   checks then fail with ``argument of type 'NoneType' is not iterable`` as
   soon as any alert fires for a managed namespace. Set the key to a list —
   ``whitelisted_alerts: []`` at minimum, as ``environments/ci.yml`` does with
   real entries — whenever Prometheus is enabled.

**Disable metrics.** Set it at the top level — ``config.metrics.enabled:
false`` — so that all three components agree. Metric generation stops and the
shared volume and its claim disappear; the API's ``/api/metrics`` endpoint
still exists and simply reports nothing. Disabling metrics for one component
only (for example ``collectController.config.metrics.enabled: false``) removes
the claim while the other pods still mount it, and those pods will not start.

Verify what is running
----------------------

Managed namespaces carry the manager's annotations, which is the quickest way
to see its decisions:

.. code-block:: bash

   kubectl get ns -o custom-columns=\
   'NAME:.metadata.name,\
   STATUS:.metadata.annotations.manager\.cicd\.skao\.int/status,\
   SINCE:.metadata.annotations.manager\.cicd\.skao\.int/status_timestamp,\
   DUE:.metadata.annotations.manager\.cicd\.skao\.int/status_finalize_at'

Metrics are served by the API only — the controllers publish theirs by writing
to the shared volume, which the API merges:

.. code-block:: bash

   # in-cluster, HTTPS Service (the chart default). The Service is
   # <fullname>-api-svc, which is just the release name plus -api-svc when the
   # release is named ska-ser-namespace-manager.
   kubectl get svc -l app.kubernetes.io/component=api
   kubectl port-forward svc/ska-ser-namespace-manager-api-svc 8443:443
   curl -k https://localhost:8443/api/metrics

   # local process or plain-HTTP deployment
   curl http://localhost:8080/api/metrics

Expect ``namespace_manager_ns_status`` for each managed namespace, plus
``namespace_manager_ns_check_total`` and ``namespace_manager_ns_delete_total``
counters per pod. If a controller's series are missing, check that the metrics
volume is mounted in that pod and that ``config.metrics.enabled`` is true.

The controllers log every decision — adoption, each status change, each
deletion, and each notification — so ``kubectl logs`` on the collect controller
replica that owns a namespace is the fastest way to understand why a namespace
was acted on. Which replica that is follows the hash described in
:doc:`explanation-namespace-lifecycle`.
