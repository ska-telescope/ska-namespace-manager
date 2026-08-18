Configuration keys, endpoints and metrics
=========================================

Every value on this page is taken from the Pydantic models under
``src/ska_ser_namespace_manager/`` and from the Helm chart in
``charts/ska-ser-namespace-manager/``. Keys are written exactly as they must
appear in YAML: no field has an alias, so the YAML key is always the Python
attribute name, in ``snake_case``.

How configuration reaches a process
-----------------------------------

Each of the three components loads one configuration model from the location
given by ``CONFIG_PATH``:

.. list-table::
   :header-rows: 1
   :widths: 30 30 40

   * - Entrypoint
     - Model
     - Started by the chart as
   * - ``src/api.py``
     - ``APIConfig``
     - ``Deployment``, the image's default command
   * - ``src/collect_controller.py``
     - ``CollectControllerConfig``
     - ``StatefulSet``
   * - ``src/action_controller.py``
     - ``ActionControllerConfig``
     - ``Deployment``

``CONFIG_PATH`` may point at a single YAML file or at a directory:

* **A file** is loaded as-is. This is the built-in default,
  ``/etc/config/config.yml``.
* **A directory** — what the chart always mounts — is loaded by reading every
  non-hidden ``*.yml`` / ``*.yaml`` file in alphabetical order and deep-merging
  them. Later filenames win, nested mappings merge key by key, lists are
  replaced wholesale, and a ``null`` in a later file leaves the earlier value
  untouched. The chart writes its rendered configuration to ``00-base.yml``, so
  any file projected alongside it sorts later and overrides it.

Two behaviours are worth knowing before debugging a configuration problem:

* **Unknown keys are ignored silently.** No model sets ``extra="forbid"``, so a
  misspelled or camelCase key (``pkiPath``, ``leaseTtl``, ``whitelistedAlerts``)
  is accepted and dropped without a warning.
* **An unreadable configuration falls back to model defaults.** If the file or
  directory cannot be read or parsed, the loader logs a warning and constructs
  the model with defaults. For the two controllers that fails immediately,
  because ``context``, ``leader_election`` and (for the action controller)
  ``namespaces`` are required. The API, whose fields are all optional, starts
  with defaults instead.

Duration values
---------------

Durations are parsed by ``parse_timedelta`` — not by ``humanfriendly`` — with
the regular expression ``(\d+(\.\d+)?)([smhdw])``, applied case-insensitively
after stripping spaces.

.. list-table::
   :header-rows: 1
   :widths: 25 25 50

   * - Written as
     - Parsed as
     - Note
   * - ``30s``, ``5m``, ``2h``, ``7d``, ``2w``
     - 30 s, 5 min, 2 h, 7 days, 2 weeks
     - ``s``, ``m``, ``h``, ``d`` and ``w`` are the only units
   * - ``1h30m``
     - 1 h 30 min
     - Units concatenate, in any order
   * - ``0.5h``
     - 30 min
     - Fractional values are allowed
   * - ``300``
     - **zero**
     - A number with no unit matches nothing and yields ``0``
   * - ``5min``, ``1y``
     - 5 min, **zero**
     - Only the first letter is read, so ``min`` works and ``y`` does not

Because a unitless value silently becomes zero, always write the unit. The
fields parsed this way are ``lease_ttl``, ``ttl``, ``settling_period``,
``grace_period``, ``gitlab.cache_ttl`` and ``gitlab.request_timeout``. Three
adjacent fields are **plain numbers, not durations**:
``people_database.cache_ttl`` (seconds), ``heartbeat.max_age_seconds``
(seconds), and ``gitlab.cache_max_entries`` (a count).

Environment variables
---------------------

.. list-table::
   :header-rows: 1
   :widths: 20 25 55

   * - Variable
     - Default
     - Purpose
   * - ``CONFIG_PATH``
     - ``/etc/config/config.yml``
     - Configuration file or directory. The chart sets it to ``configPath``
       (``/etc/config``) for all three components.
   * - ``LOG_LEVEL``
     - ``INFO``
     - Root log level, any name accepted by ``logging.getLevelName``.
   * - ``HOSTNAME``
     - set by Kubernetes
     - Identifies the replica. Names the metrics file (``<pod>.prom``) and is
       matched against the discovered replica list to decide which namespaces
       this replica checks.
   * - ``POD_NAME``
     - unset
     - Fallback when ``HOSTNAME`` is absent. If neither is set the process uses
       ``local-<pid>``.

Command-line arguments
----------------------

Both controllers accept exactly one optional flag; the API accepts none.

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Flag
     - Components
     - Effect
   * - ``--kubeconfig <path>``
     - collect controller, action controller
     - Authenticate against the cluster with this kubeconfig instead of the
       in-cluster service account. Without it the process loads the in-cluster
       configuration and **exits with an error if that is unavailable**, which
       is why a local run outside a cluster must pass this flag.

The first argument is always the entrypoint script path, passed to the image's
``python3 -u`` entrypoint; the chart appends each component's ``extraArgs``
after it, which is how ``--kubeconfig`` would be supplied in a deployment.

Blocks shared by all components
-------------------------------

``context``
~~~~~~~~~~~

Required by both controllers and rendered entirely by the chart — do not write
it by hand.

.. list-table::
   :header-rows: 1
   :widths: 25 15 15 45

   * - Key
     - Type
     - Default
     - Purpose
   * - ``namespace``
     - string
     - required
     - Namespace the controller runs in. Added to the never-managed list.
   * - ``service_account``
     - string
     - required
     - Used when discovering sibling replicas.
   * - ``image``
     - string
     - required
     - Image reference, recorded for traceability.
   * - ``config_path``
     - string
     - required
     - Where the configuration was mounted.
   * - ``config_secret``
     - string
     - required
     - Name of the Secret holding ``00-base.yml``.
   * - ``stateful_set_name``
     - string
     - ``null``
     - Collect controller only. Used to derive replica names for sharding;
       without it the controller falls back to live pod discovery.

``leader_election``
~~~~~~~~~~~~~~~~~~~

Required by both controllers.

.. list-table::
   :header-rows: 1
   :widths: 25 15 20 40

   * - Key
     - Type
     - Default
     - Purpose
   * - ``enabled``
     - bool
     - ``false``
     - Whether to elect a leader. The chart overrides this to ``replicas > 1``,
       so the value in ``values.yaml`` never reaches the process.
   * - ``path``
     - string
     - ``/etc/leader``
     - Directory holding the lock and lease files; must be shared between
       replicas.
   * - ``lease_ttl``
     - duration
     - ``5s``
     - Lease lifetime. The holder renews every ``lease_ttl / 2``; a lease older
       than ``2 × lease_ttl`` is treated as abandoned.
   * - ``lock_path``
     - string
     - derived
     - Always recomputed as ``<path>/lock``; a configured value is discarded.
   * - ``lease_path``
     - string
     - derived
     - Always recomputed as ``<path>/lease``; a configured value is discarded.

``metrics``
~~~~~~~~~~~

Accepted by all three components.

.. list-table::
   :header-rows: 1
   :widths: 25 15 20 40

   * - Key
     - Type
     - Default
     - Purpose
   * - ``enabled``
     - bool
     - ``true``
     - Gates metric generation. The chart also uses it to decide whether to
       create and mount the metrics volume.
   * - ``registry_path``
     - string
     - ``metrics``
     - Directory holding the ``*.prom`` files. Created on startup if missing.
       The chart sets ``/etc/metrics``.
   * - ``pvc.storageClassName``
     - string
     - ``nfss1``
     - **Chart-only.** Sits inside ``config.metrics`` in ``values.yaml`` but is
       not part of the model, so the process ignores it. It sizes the shared
       metrics ``PersistentVolumeClaim``.
   * - ``pvc.size``
     - string
     - ``1Gi``
     - **Chart-only**, as above.

API configuration
-----------------

Top level of ``api.config``.

.. list-table::
   :header-rows: 1
   :widths: 25 15 20 40

   * - Key
     - Type
     - Default
     - Purpose
   * - ``http_port``
     - int
     - ``8080``
     - Port used when HTTPS is disabled.
   * - ``https_port``
     - int
     - ``9443``
     - Port used when HTTPS is enabled.
   * - ``https_enabled``
     - bool
     - ``false``
     - Serve TLS. The chart derives it from
       ``api.service.https.enabled``, so it is ``true`` by default in a
       deployment.
   * - ``pki_path``
     - string
     - ``/etc/pki``
     - Directory holding the TLS material.
   * - ``ca_path`` / ``cert_path`` / ``key_path``
     - string
     - derived
     - Set to ``<pki_path>/ca.crt``, ``tls.crt`` and ``tls.key`` when
       ``https_enabled`` is true, otherwise ``null``. Configured values are
       overwritten.
   * - ``people_database``
     - object
     - ``{enabled: false}``
     - See below. Note the effective default: omit the block entirely and the
       People Database is **off**, even though the block's own ``enabled``
       default is ``true``.
   * - ``metrics``
     - object
     - see ``metrics``
     - Where the API reads the ``*.prom`` files it merges.

``api.config.people_database``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 25 35

   * - Key
     - Type
     - Default
     - Purpose
   * - ``enabled``
     - bool
     - ``true`` (within the block)
     - When false, ``spreadsheet_id`` and ``credentials`` may be omitted; the
       API still starts and passes readiness, and ``/api/people`` answers
       ``not found``.
   * - ``spreadsheet_id``
     - string
     - ``null``
     - Required when enabled.
   * - ``spreadsheet_range``
     - string
     - ``System Team API!A2:Z1001``
     - Sheet range to read.
   * - ``cache_ttl``
     - int (seconds)
     - ``3600``
     - How long a fetched copy is reused.
   * - ``credentials``
     - object
     - ``null``
     - Google service account. Required when enabled.

An empty mapping (``people_database: {}``) is rewritten to
``{enabled: false}``, which is what lets the chart render an empty credentials
skeleton without failing validation. When the block is enabled,
``spreadsheet_id``, ``credentials.project_id``, ``credentials.private_key`` and
``credentials.client_email`` must all be non-empty or the process exits with a
validation error naming the missing keys.

``credentials`` takes the fields of a Google service-account key. Six of them
have no default and are required as soon as the block is present at all:
``project_id``, ``private_key_id``, ``private_key``, ``client_email``,
``client_id`` and ``client_x509_cert_url``. The rest default to the standard
Google values: ``type`` (``service_account``), ``universe_domain``
(``googleapis.com``), ``auth_uri``, ``token_uri`` and
``auth_provider_x509_cert_url``.

Because the six are required whenever ``credentials`` exists, a
partially-filled block fails validation even when the intent was to run without
the People Database — omit the block, or write ``people_database: {}``, instead
of leaving its keys empty. Supply real values from a Secret, never from
committed values.

Collect controller configuration
--------------------------------

Top level of ``collectController.config``: ``context``, ``leader_election``,
``metrics`` and ``heartbeat`` as described above, plus the blocks below.

``namespaces``
~~~~~~~~~~~~~~

A list. Each entry is a matcher (see `Matching namespaces`_) plus:

.. list-table::
   :header-rows: 1
   :widths: 25 15 20 40

   * - Key
     - Type
     - Default
     - Purpose
   * - ``ttl``
     - duration
     - ``null``
     - Age, measured from the namespace's ``creationTimestamp``, after which it
       becomes ``stale``. ``null`` disables the staleness check for this entry.
   * - ``settling_period``
     - duration
     - ``5m``
     - How long a namespace stays ``unstable`` before becoming ``failing``.
   * - ``grace_period``
     - duration
     - ``1m``
     - How long a namespace stays ``failing`` before becoming ``failed``. The
       chart's default entry sets ``2m``.
   * - ``checks.cancelled``
     - bool
     - ``false``
     - Look up the originating GitLab pipeline and mark the namespace
       ``cancelled`` when the pipeline was cancelled or no longer exists.
       Requires the ``gitlab`` block to be enabled.
   * - ``checks.superseded``
     - bool
     - ``false``
     - Mark older deployments of the same branch or merge request
       ``superseded``.
   * - ``actions.check-namespace.schedule``
     - string
     - ``60s``
     - Interval between health checks for a matched namespace.
       ``check-namespace`` is the only supported action name. An empty,
       unparseable or non-positive value falls back to 60 s with a warning.

``prometheus``
~~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 20 40

   * - Key
     - Type
     - Default
     - Purpose
   * - ``enabled``
     - bool
     - ``true``
     - When false, health is judged from Deployment, StatefulSet and ReplicaSet
       replica counts instead of alerts.
   * - ``url``
     - string
     - ``null``
     - Base URL; alerts are read from ``<url>/api/v1/alerts`` with a 20 s
       timeout.
   * - ``ca``
     - string
     - ``null``
     - CA certificate, inline PEM. Written to a temporary file at startup and
       used to verify the connection.
   * - ``ca_path``
     - string
     - derived
     - Path of that temporary file; do not set it yourself.
   * - ``insecure``
     - bool
     - ``false``
     - Skip certificate verification. Takes precedence over ``ca``. The chart
       ships ``true`` for both ``prometheus`` and ``people_api``.
   * - ``datacentre``
     - string
     - ``null``
     - When set, only alerts carrying a matching ``datacentre`` label are
       considered.
   * - ``whitelisted_alerts``
     - list of strings
     - ``[]``
     - Alert names that do not make a namespace unhealthy unless their
       ``severity`` is ``critical``. Write a list or omit the key — an explicit
       ``null`` (which is what ``values.yaml`` ships) makes the value ``None``
       and every alert evaluation then raises, so each health check fails until
       a list is supplied.

``gitlab``
~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 20 40

   * - Key
     - Type
     - Default
     - Purpose
   * - ``enabled``
     - bool
     - ``false``
     - Enables pipeline-status lookups. **A token is mandatory once this is
       true**: the process raises at startup otherwise.
   * - ``api_base``
     - string
     - ``https://gitlab.com``
     - GitLab base URL.
   * - ``requester``
     - string
     - ``""``
     - Identity sent with API calls.
   * - ``private_token``
     - string
     - ``null``
     - GitLab token. Project this from a Secret rather than Helm values.
   * - ``cache_ttl``
     - duration
     - ``5m``
     - How long a pipeline status is reused.
   * - ``cache_max_entries``
     - int
     - ``10000``
     - Cache capacity.
   * - ``request_timeout``
     - duration
     - ``10s``
     - Per-request deadline. Supported, but absent from ``values.yaml``.

``heartbeat``
~~~~~~~~~~~~~

.. list-table::
   :header-rows: 1
   :widths: 25 15 25 35

   * - Key
     - Type
     - Default
     - Purpose
   * - ``path``
     - string
     - ``/tmp/collect-controller-heartbeat``
     - File touched on every reconciliation pass. Resolved to an absolute path
       at load time.
   * - ``max_age_seconds``
     - int
     - ``60``
     - Age at which the file is considered stale. Read only by the chart's
       liveness ``exec`` probe, not by the application.

``people_api``
~~~~~~~~~~~~~~

Accepts ``url`` (default ``http://localhost:8080``), ``ca``, ``ca_path`` and
``insecure``, and the chart injects the in-cluster API URL. No code currently
reads this block — the collect controller does not call the People API — so
setting it has no effect today.

Action controller configuration
-------------------------------

Top level of ``actionController.config``: ``context``, ``leader_election`` and
``metrics`` as above, plus ``notifier.token`` (the Slack bot token; when unset,
notifications are logged as disabled rather than failing) and a **required**
``namespaces`` list.

Each ``namespaces`` entry is a matcher plus one block per status. Every block
takes the same three keys:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Key
     - Meaning
   * - ``delete``
     - Delete the namespace while it holds this status.
   * - ``notify_on_delete``
     - Send a deletion message to the namespace owner.
   * - ``notify_on_status``
     - Send a message when the namespace enters this status.

The defaults differ per status:

.. list-table::
   :header-rows: 1
   :widths: 22 16 26 26

   * - Status block
     - ``delete``
     - ``notify_on_delete``
     - ``notify_on_status``
   * - ``stale``
     - ``true``
     - ``true``
     - ``false``
   * - ``failed``
     - ``true``
     - ``true``
     - ``false``
   * - ``failing``
     - ``false``
     - ``false``
     - ``true``
   * - ``unstable``
     - ``false``
     - ``false``
     - ``true``
   * - ``cancelled``
     - ``true``
     - ``false``
     - ``true``
   * - ``superseded``
     - ``true``
     - ``false``
     - ``true``

Two constraints are not obvious from the schema:

* Only ``stale``, ``failed``, ``cancelled`` and ``superseded`` are ever
  deleted. Setting ``delete: true`` under ``failing`` or ``unstable`` has no
  effect, because no deletion task looks for those statuses.
* Only ``unstable``, ``failing``, ``cancelled`` and ``superseded`` produce
  status notifications. ``notify_on_status`` under ``stale`` or ``failed`` is
  never consulted.

Matching namespaces
-------------------

Both controllers select namespaces with the same three keys, and any entry may
combine them:

.. list-table::
   :header-rows: 1
   :widths: 15 15 20 50

   * - Key
     - Type
     - Score
     - Meaning
   * - ``names``
     - list of regex
     - 1
     - Matches when a pattern matches the whole namespace name
       (``re.fullmatch``).
   * - ``any``
     - list of conditions
     - 2
     - Matches when **at least one** condition matches.
   * - ``all``
     - list of conditions
     - 4
     - Matches when **every** condition matches.

A condition is a mapping with ``labels`` and/or ``annotations``, each a
key/value mapping compared for exact equality. Scores are added per entry and
the highest-scoring entry wins, which is what gives the documented precedence
``all > any > names``. A namespace matching no entry is not managed at all.

``kube-system``, ``kube-public``, ``kube-node-lease``, ``default`` and the
namespace the controller itself runs in are excluded regardless of matchers.

HTTP endpoints
--------------

Only the API listens on a port. It serves HTTP on ``http_port`` or HTTPS on
``https_port``, never both.

.. list-table::
   :header-rows: 1
   :widths: 30 55 15

   * - Path
     - Purpose
     - Status codes
   * - ``GET /health/liveness``
     - Always answers while the process is up.
     - 200
   * - ``GET /health/readiness``
     - Reports whether the People Database copy could be refreshed. With the
       People Database disabled it is always ready.
     - 200, 500
   * - ``GET /api/people``
     - Ownership lookup. Accepts ``email``, ``slack_id`` and
       ``gitlab_handle`` query parameters, plus ``ignore_not_found=true`` to
       answer 200 instead of 404 for a miss.
     - 200, 404
   * - ``GET /api/metrics``
     - Prometheus exposition, merged across every component's metrics file.
     - 200

FastAPI also serves its own ``/docs`` and ``/openapi.json``. None of the routes
authenticate or authorise: exposure is governed entirely by the Service type,
which the chart defaults to ``LoadBalancer``.

The controllers expose no HTTP port at all: their liveness signal is the
heartbeat file (collect controller) and process liveness (action controller).

Metrics
-------

Three metrics are published, all by every component that has something to
record, and all merged into one response by the API.

.. list-table::
   :header-rows: 1
   :widths: 32 12 26 30

   * - Metric
     - Type
     - Labels
     - Meaning
   * - ``namespace_manager_ns_status``
     - Gauge
     - ``namespace``, ``project``, ``projectId``, ``pipelineId``, ``team``,
       ``user``, ``environment``
     - Current status of a managed namespace, encoded numerically. Labels come
       from the namespace's ``cicd.skao.int/*`` labels, defaulting to
       ``unknown``.
   * - ``namespace_manager_ns_check_total``
     - Counter
     - ``owner``, ``result``
     - Health-check executions per replica, with ``result`` either ``success``
       or ``failure``.
   * - ``namespace_manager_ns_delete_total``
     - Counter
     - ``owner``, ``status``
     - Namespace deletions, counted by the status that triggered them.

``owner`` is the pod name. The gauge's values are:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Status
     - Value
     - Set by
   * - ``ok``
     - ``0``
     - Collect controller
   * - ``stale``
     - ``1``
     - Collect controller
   * - ``failing``
     - ``2``
     - Collect controller
   * - ``failed``
     - ``3``
     - Collect controller
   * - ``unstable``
     - ``4``
     - Collect controller
   * - ``cancelled``
     - ``5``
     - Collect controller
   * - ``superseded``
     - ``6``
     - Collect controller
   * - ``unknown``
     - ``-1``
     - Collect controller

Each process writes its own metrics to ``<registry_path>/<pod name>.prom`` in
Prometheus text format and re-reads that file on startup, so counters survive a
restart. Files belonging to pods that no longer exist are deleted by the
collect controller's leader once a minute.

Scraping metrics
~~~~~~~~~~~~~~~~

There is no per-pod metrics port, and the chart defines no ``hostPort`` and no
dedicated metrics Service, so the endpoint to scrape depends on where the API
is running:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Context
     - Endpoint
   * - Local process
     - ``curl http://localhost:8080/api/metrics`` — the API's HTTP port, with
       ``https_enabled`` left at its default of ``false``.
   * - Container
     - Same path on the port the container publishes: ``8080`` for HTTP, or
       ``9443`` over HTTPS once ``https_enabled`` is true.
   * - Helm, in-cluster
     - ``https://<fullname>-api-svc.<namespace>.svc:443/api/metrics``, where
       ``<fullname>`` is ``<release>-<chart name>``, collapsing to just the
       release name when the release name already contains the chart name (so
       the default release gives ``ska-ser-namespace-manager-api-svc``). The
       chart's API Service defaults to ``LoadBalancer`` with HTTPS on port
       ``443``; with a self-signed certificate a scrape needs the generated CA
       or ``insecure_skip_verify``. Set ``api.service.https.enabled: false`` to
       serve plain HTTP on port ``80`` instead.
   * - Helm, collect controller
     - Not scrapeable directly. The collect controller's Service is headless
       and publishes only port ``80`` named ``controller``, which nothing
       listens on; its metrics reach Prometheus through the shared volume and
       the API's ``/api/metrics``.

Annotations and labels
----------------------

The manager writes its own state under ``manager.cicd.skao.int/``:

.. list-table::
   :header-rows: 1
   :widths: 40 60

   * - Annotation
     - Meaning
   * - ``managed``
     - ``true`` once the namespace has been adopted.
   * - ``namespace``
     - The namespace's own name, recorded at adoption.
   * - ``status``
     - Current status: one of ``ok``, ``stale``, ``unstable``, ``failing``,
       ``failed``, ``cancelled``, ``superseded``, ``unknown``.
   * - ``status_timestamp``
     - When the status last changed, in UTC.
   * - ``status_timeframe``
     - Human-readable window before the pending action, e.g. ``5 minutes``.
   * - ``status_finalize_at``
     - UTC timestamp at which the pending action becomes due.
   * - ``failing_resources``
     - JSON list of failing resource names, or of alert objects when
       Prometheus is the source.
   * - ``notified_timestamp``
     - When the owner was last notified. Cleared on every status change.
   * - ``notified_status``
     - Status the owner was last notified about.

Two further keys, ``manager.cicd.skao.int/action`` and
``manager.cicd.skao.int/spec_hash``, are declared in ``core/types.py`` but never
written by the current code.

It reads, but never writes, the ``cicd.skao.int/*`` labels and annotations set
by the SKAO CI templates. The ones that change behaviour are the labels
``projectId``, ``pipelineId``, ``jobId``, ``job``, ``branch`` and ``mrId``,
which identify the originating pipeline for the ``cancelled`` and
``superseded`` checks, the labels ``project``, ``team``, ``author``,
``environmentTier`` and ``projectId``, which become metric labels, and the
annotations ``notificationAddress`` — without which a namespace is acted on
silently — and ``jobUrl``, quoted in notifications.

Bundled tooling
---------------

The image is built from the SKAO base images, with dependencies resolved from
``uv.lock``:

.. list-table::
   :header-rows: 1
   :widths: 30 20 50

   * - Component
     - Version
     - Role
   * - ``artefact.skao.int/ska-build-python``
     - ``0.5.0``
     - Build stage: resolves and installs the locked dependencies with ``uv``.
   * - ``artefact.skao.int/ska-python``
     - ``0.3.1``
     - Runtime stage; carries the virtual environment copied from the build
       stage.
   * - Python
     - ``>=3.10,<4.0``
     - Interpreter range the project supports.
   * - ``ska-cicd-services-api``
     - ``1.2.0`` (pinned exactly)
     - SKAO People Database client.
   * - ``kubernetes``
     - ``>=35.0.0,<36.0.0``
     - Kubernetes API client.
   * - ``fastapi`` / ``uvicorn``
     - ``>=0.136.1,<0.137.0`` / ``>=0.46.0,<0.47.0``
     - REST API and ASGI server.
   * - ``prometheus-client``
     - ``>=0.25.0,<0.26.0``
     - Metrics registry and text format.
   * - ``slack-bolt``
     - ``>=1.28.0,<2.0.0``
     - Slack notifications.
   * - ``filelock``
     - ``>=3.29.0,<4.0.0``
     - Leader election lock.

The image's entrypoint is ``python3 -u`` and its default command is
``/opt/ska_ser_namespace_manager/api.py``; the chart overrides the command with
the controller entrypoints. There are no other external binaries: nothing
shells out to ``kubectl``, ``helm`` or ``git``.
