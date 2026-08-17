Deploy and try the Namespace Manager locally
============================================

This page walks through a complete local run: build the image into a local
cluster, deploy the Helm chart with the bundled ``local`` environment, then
create a namespace and watch the manager adopt it, annotate it, and delete it
once its TTL expires. Every configuration key mentioned here is described in
:doc:`reference-configuration`.

Before you start
----------------

You need a running local Kubernetes cluster and a working ``kubectl`` context.
Please check `ska-cicd-deploy-minikube <https://gitlab.com/ska-telescope/sdi/ska-cicd-deploy-minikube>`_,
which provisions a minikube cluster configured the way the SKAO clusters are.

The ``local`` environment values need nothing else: Vault, the SKAO People
Database, Prometheus, GitLab and Slack are all switched off, so the manager runs
on what the cluster already provides.

Set up a working copy
---------------------

The repository uses the shared SKAO tooling submodule, and ``uv`` for
dependencies:

.. code-block:: bash

   git clone git@gitlab.com:ska-telescope/ska-ser-namespace-manager.git
   cd ska-ser-namespace-manager
   git submodule update --init --recursive
   uv sync

Formatting, linting and tests go through the ``Makefile``, which runs the tools
inside that environment:

.. code-block:: bash

   make python-format
   make python-lint
   make python-test          # unit tests, ./tests/unit
   make docs-build html      # this documentation, into docs/build/html

The integration suite under ``tests/integration`` needs a deployed chart and is
run with ``make k8s-test``; it skips itself unless ``NSTEST_MANAGER_NAMESPACE``
or ``KUBE_NAMESPACE`` is set.

Build the image into the cluster
--------------------------------

``make oci-build-all`` builds but never pushes, so the image has to end up
inside the cluster's own container runtime — otherwise the pods sit in
``ImagePullBackOff``. Point your Docker client at minikube's daemon and build
there:

.. code-block:: bash

   source .venv/bin/activate
   eval $(minikube docker-env)
   make oci-build-all CAR_OCI_REGISTRY_HOST=localhost:5000

Note the tag that comes out — it is the version in ``.release`` plus ``-dirty``
when the working tree has uncommitted changes:

.. code-block:: bash

   docker images | grep ska-ser-namespace-manager
   # localhost:5000/ska-ser-namespace-manager   0.3.2-dirty   ...

Point the local values at that image
------------------------------------

``charts/ska-ser-namespace-manager/environments/local.yml`` exists for exactly
this purpose. Set its ``image`` block to the tag you just built:

.. code-block:: yaml

   image:
     repository: localhost:5000/ska-ser-namespace-manager
     pullPolicy: IfNotPresent
     tag: 0.3.2-dirty

Deploy the chart
----------------

.. code-block:: bash

   ENVIRONMENT=local KUBE_NAMESPACE=ska-ser-namespace-manager make k8s-install-chart

``ENVIRONMENT=local`` layers ``environments/local.yml`` on top of
``environments/all.yml``, both passed through ``envsubst``. Use
``make k8s-template-chart`` with the same variables to render the manifests
without installing, and ``make k8s-uninstall-chart`` to remove the release.

Three workloads should come up — the API Deployment, the collect controller
StatefulSet, and the action controller Deployment:

.. code-block:: bash

   kubectl get pods -n ska-ser-namespace-manager

What the ``local`` values give up, and what it buys you:

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Disabled
     - Consequence
   * - People Database
     - The API starts and passes readiness, and ``GET /api/people`` answers
       ``not found``. Namespaces are still managed; owners just cannot be
       resolved.
   * - Prometheus
     - Health checks fall back to the Kubernetes API and treat any Deployment,
       StatefulSet or ReplicaSet with fewer available replicas than desired as
       failing — which is what makes an unhealthy namespace easy to demo.
   * - GitLab
     - The ``cancelled`` check is off, so namespaces are never marked
       cancelled. ``superseded`` is off too; it needs ``cicd.skao.int`` labels
       that only the SKAO CI templates set.
   * - Slack
     - No bot token, so the action controller logs a warning at startup and
       deletes namespaces silently.

Every component runs a single replica, so leader election is off and the chart
provisions no lock volume.

Watch it manage a namespace
---------------------------

The ``local`` values manage anything matching ``ci-.*``, with a five minute TTL
and a check every thirty seconds. Create a namespace:

.. code-block:: bash

   kubectl create ns ci-test-ns

The collect controller's leader adopts it within a second or two, then starts a
check thread for it:

.. code-block:: text

   $ kubectl logs -n ska-ser-namespace-manager ska-ser-namespace-manager-collect-controller-0
   ... [level=INFO]: Loaded in-cluster kubeconfig
   ... [level=INFO]: Loading configuration for 'CollectControllerConfig' from /etc/config (directory)
   ... [level=INFO]: Managing task 'check_new_namespaces'
   ... [level=INFO]: Managing task 'check_superseded_namespaces'
   ... [level=INFO]: Metrics registry at: /etc/metrics
   ... [level=INFO]: Managing task 'check_assigned_namespaces'
   ... [level=INFO]: Managing task 'generate_metrics'
   ... [level=INFO]: Managing task 'reconcile_metrics_files'
   ... [level=INFO]: Managing new namespace 'ci-test-ns'
   ... [level=INFO]: Starting namespace check thread 'namespace-check-ci-test-ns' for namespace 'ci-test-ns' with period '30.0s'
   ... [level=INFO]: Starting check for namespace 'ci-test-ns'
   ... [level=INFO]: Setting namespace 'ci-test-ns' status: NamespaceStatus.OK

Two things are worth noticing in that output. The configuration is loaded twice,
once as ``CollectControllerConfig`` and once as ``CollectorConfig``, from the
same directory — that is expected. And the check period comes from the matched
entry's ``check-namespace`` schedule, not from a global setting.

The decision is recorded on the namespace itself:

.. code-block:: text

   $ kubectl describe namespace ci-test-ns
   Name:         ci-test-ns
   Labels:       kubernetes.io/metadata.name=ci-test-ns
   Annotations:  manager.cicd.skao.int/failing_resources: []
                 manager.cicd.skao.int/managed: true
                 manager.cicd.skao.int/namespace: ci-test-ns
                 manager.cicd.skao.int/status: ok
                 manager.cicd.skao.int/status_finalize_at: 2026-08-17T09:55:41.915951Z
                 manager.cicd.skao.int/status_timeframe: 5 minutes
                 manager.cicd.skao.int/status_timestamp: 2026-08-17T09:50:41.915951Z
   Status:       Active

``status_finalize_at`` is the TTL deadline and ``status_timeframe`` the same
window in words — both are what a Slack notification would quote. Empty
``failing_resources`` means the fallback health check found nothing wrong.

After five minutes the next check marks the namespace ``stale``, the action
controller deletes it, and the collect controller tears down the thread and
drops its metrics series:

.. code-block:: text

   ... [level=INFO]: Namespace 'ci-test-ns' status remains unchanged: NamespaceStatus.OK
   ... [level=INFO]: Starting check for namespace 'ci-test-ns'
   ... [level=INFO]: Setting namespace 'ci-test-ns' status: NamespaceStatus.STALE
   ... [level=INFO]: Removed namespace thread for 'ci-test-ns'
   ... [level=INFO]: Removed metrics for namespace 'ci-test-ns'

The deletion itself is logged by the *action* controller, so check both when
following a namespace through its lifecycle:

.. code-block:: bash

   kubectl logs -n ska-ser-namespace-manager -l app.kubernetes.io/component=action-controller

Metrics are served by the API only — the controllers publish theirs by writing
``<pod>.prom`` files to the shared volume, which the API merges:

.. code-block:: bash

   kubectl port-forward -n ska-ser-namespace-manager svc/ska-ser-namespace-manager-api-svc 8443:443
   curl -k https://localhost:8443/api/metrics

Expect ``namespace_manager_ns_status`` per managed namespace, plus
``namespace_manager_ns_check_total`` and ``namespace_manager_ns_delete_total``
per pod.

Finally, tidy up:

.. code-block:: bash

   ENVIRONMENT=local KUBE_NAMESPACE=ska-ser-namespace-manager make k8s-uninstall-chart

Moving to a real cluster
------------------------

Beyond the local demo, the values you will actually set are:

.. list-table::
   :header-rows: 1
   :widths: 42 58

   * - Value
     - Why
   * - ``collectController.config.namespaces`` and
       ``actionController.config.namespaces``
     - The two matcher lists. The collect controller decides status, the action
       controller decides what to do about it, so a namespace missing from
       either list is only half managed. ``names`` entries are full-match
       regular expressions.
   * - ``<entry>.ttl``, ``.settling_period``, ``.grace_period``
     - Lifecycle timings. Durations always need a unit — ``5m``, not ``300``.
   * - ``<entry>.checks.cancelled`` / ``.superseded``
     - Enable the GitLab-backed checks. ``cancelled`` also requires
       ``collectController.config.gitlab.enabled: true`` **and** a token, or the
       controller fails at startup by design.
   * - ``api.config.people_database``
     - Either supply ``spreadsheet_id`` and ``credentials``, or set
       ``enabled: false``. The chart's own defaults render a credentials
       skeleton that fails validation, so a stock install without either
       crash-loops the API.
   * - ``collectController.config.prometheus``
     - ``url`` plus ``ca`` or ``insecure``. Also set ``whitelisted_alerts`` to a
       list: the default value arrives as ``null``, which makes every health
       check raise once an alert fires.
   * - ``actionController.config.notifier.token``
     - Slack bot token. Owners come from each namespace's
       ``cicd.skao.int/notificationAddress`` annotation; namespaces without one
       are acted on silently.
   * - ``config.metrics.pvc.storageClassName`` and
       ``<component>.pvc.leaderElection.storageClassName``
     - Both claims are ``ReadWriteMany``, and the leader-election volume must
       support ``flock``. The leader claim is created as soon as a component has
       more than one replica, and has no storage class by default, so it stays
       ``Pending`` until you set one.
   * - ``<component>.replicas``
     - Namespaces are shared across collect-controller replicas by hash. Keep
       ``actionController.replicas: 1``: its delete and notify loops are not
       leader-gated, and its leader-election volume is mounted read-only.

Chart behaviour worth knowing
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A few chart values do not behave the way their names suggest:

* ``<component>.image.pullPolicy`` is ignored — the top-level
  ``image.pullPolicy`` always wins. ``repository`` and ``tag`` do honour the
  per-component override.
* ``api.service.https.type`` sets the Service type **in both modes**;
  ``api.service.http.type`` and ``http.annotations`` are never read.
* The API probes hardcode ``port: 9443`` and ``scheme: HTTPS``. If you set
  ``api.service.https.enabled: false``, override all three probes as well or the
  pod never becomes ready.
* ``api.pki.createSelfSignedCert: false`` requires ``api.pki.ca``, ``.cert``
  and ``.key`` together; on its own it fails the render.
* ``<component>.apiPriorityAndFairness`` renders a
  ``PriorityLevelConfiguration`` with ``apiVersion: v1`` instead of
  ``flowcontrol.apiserver.k8s.io/v1``, so the API server rejects it. Leave it
  off.
* ``<component>.config.leader_election.enabled`` is overwritten by the chart
  with ``replicas > 1``, so setting it has no effect.
* Disable metrics at the top level (``config.metrics.enabled: false``) so all
  three components agree. Disabling it for one component removes the shared
  claim while the other pods still mount it, and those pods will not start.
* There is no ``extraVolumes``, ``sidecars``, ``serviceAccount.create`` or
  existing-claim reuse. ``<component>.labels`` and ``.annotations`` reach the
  pod template only; the top-level ``labels`` is the only way to label the
  workload object. Anything else goes through ``extraDeploy``.
