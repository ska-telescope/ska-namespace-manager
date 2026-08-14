# SKA Namespace Manager

SKA Namespace Manager manages CI/CD namespaces in a Kubernetes cluster. It
keeps temporary environments visible, applies lifecycle policies, exports
namespace health metrics, and deletes namespaces that are stale, failed,
cancelled, or superseded.

Full documentation lives under [`docs/src`](docs/src) and is built with
`make docs-build html`:

- [Getting started](docs/src/howto-run-and-deploy.rst) — run it locally, in a
  container, or deploy the Helm chart.
- [Reference](docs/src/reference-configuration.rst) — configuration keys,
  endpoints, metrics and chart values.
- [How it works](docs/src/explanation-namespace-lifecycle.rst) — matching, the
  status state machine, sharding and leader election.

The service is designed for CI/CD clusters where resource demand is bursty and
unpredictable. It helps operators and developers by:

- applying fair lifecycle limits to temporary CI namespaces;
- detecting namespaces that are wasting resources or failing health checks;
- notifying namespace owners before or during cleanup;
- publishing Prometheus metrics for namespace status, checks, and deletion
  actions.

## Runtime Architecture

The Helm chart deploys three runtime surfaces:

- **API** (`src/api.py`): FastAPI service for health probes, People API-backed
  ownership lookups, and merged Prometheus metrics.
- **Collect controller** (`src/collect_controller.py`): leader-aware controller
  that finds configured namespaces, marks them as managed, runs periodic
  in-process health checks, and writes namespace status annotations and metrics.
- **Action controller** (`src/action_controller.py`): leader-aware controller
  that reads status annotations, deletes namespaces when configured to do so,
  records deletion metrics, and sends Slack notifications.

```mermaid
flowchart LR
    prom["Prometheus"]
    gitlab["GitLab API"]

    subgraph nsm["SKA Namespace Manager (Helm release)"]
        direction TB
        collect["Collect controller<br/><i>StatefulSet</i><br/>adopt · check · annotate"]
        action["Action controller<br/><i>Deployment</i><br/>notify · delete"]
        volume[("Shared ReadWriteMany volume<br/>metrics files · leader lock")]
        api["REST API<br/><i>Deployment</i><br/>/health · /api/people · /api/metrics<br/><i>scraped by Prometheus</i>"]
    end

    k8s["Kubernetes API"]
    ns["Managed namespaces<br/>their manager.cicd.skao.int annotations<br/>hold the lifecycle state"]
    people[("SKAO People Database")]
    slack["Slack"]

    prom -- "firing alerts" --> collect
    gitlab -- "pipeline status" --> collect

    collect -- "annotate status" --> k8s
    action -- "read status, delete" --> k8s
    k8s --> ns

    collect -- "metrics, leader lock" --> volume
    action -- "metrics" --> volume
    volume -- "merged *.prom" --> api
    api -- "ownership lookup" --> people
    action -- "notifications" --> slack

    classDef controller fill:#dbeafe,stroke:#1f6feb,color:#0b2545,font-weight:bold;
    classDef service fill:#ede9fe,stroke:#8250df,color:#2d1065,font-weight:bold;
    classDef platform fill:#eef2f6,stroke:#8b98a5,color:#1c2b36;
    classDef store fill:#fff4e5,stroke:#d97706,color:#7a3e00;
    classDef integration fill:#eaf7ea,stroke:#2da44e,color:#0f3d1f;

    class collect,action controller;
    class api service;
    class k8s platform;
    class ns,people,volume store;
    class prom,gitlab,slack integration;
```

Namespace selection is driven by configured matchers. A namespace can match by
name pattern, by any label/annotation condition, or by all label/annotation
conditions. The matching precedence is `all > any > names`.

## Namespace Lifecycle

Namespace lifecycle state is stored on Kubernetes namespace annotations under
the `manager.cicd.skao.int/*` prefix. The collect controller updates the
status; the action controller acts on it.

```mermaid
stateDiagram-v2
    direction LR
    [*] --> unknown: adopted by the<br/>collect controller

    unknown --> ok: nothing failing
    unknown --> unstable: something failing
    ok --> unstable: something failing

    state "degrading, one step per check" as degrading {
        direction LR
        unstable --> failing: still failing after<br/>settling_period
        failing --> failed: still failing after<br/>grace_period
    }

    degrading --> ok: nothing failing

    state one_way <<choice>>
    unknown --> one_way
    ok --> one_way
    degrading --> one_way

    one_way --> stale: older than ttl
    one_way --> cancelled: originating pipeline<br/>cancelled or gone
    one_way --> superseded: newer deployment of<br/>the same CI identity

    state "deleted by the action controller" as deleted
    failed --> deleted
    stale --> deleted
    cancelled --> deleted
    superseded --> deleted
    deleted --> [*]

    classDef initial fill:#eef2f6,stroke:#8b98a5,color:#1c2b36;
    classDef healthy fill:#eaf7ea,stroke:#2da44e,color:#0f3d1f,font-weight:bold;
    classDef unhealthy fill:#fff4e5,stroke:#d97706,color:#7a3e00;
    classDef terminal fill:#fde8ef,stroke:#cf222e,color:#5c0011;

    class unknown initial
    class ok healthy
    class unstable,failing unhealthy
    class stale,failed,cancelled,superseded terminal
```

The supported status values are:

- `unknown`: initial status for a newly managed namespace.
- `ok`: namespace is healthy and still within its configured TTL.
- `unstable`: failing resources or matching Prometheus alerts were detected.
- `failing`: the namespace stayed unstable past its settling period.
- `failed`: the namespace stayed failing past its grace period.
- `stale`: the namespace exceeded its configured TTL.
- `cancelled`: the originating GitLab pipeline was cancelled or no longer
  found, when the cancelled check is enabled.
- `superseded`: an older namespace was replaced by a newer namespace for the
  same branch or merge request identity, when the superseded check is enabled.

For health checks, Prometheus alerts are used when Prometheus integration is
enabled. When Prometheus integration is disabled, the collector falls back to
Kubernetes Deployment, StatefulSet, and ReplicaSet replica health checks.

## Capabilities

SKA Namespace Manager currently supports:

- cleanup of CI namespaces after a configured TTL;
- cleanup of failed namespaces after unstable and failing grace windows;
- cleanup of namespaces from cancelled or deleted GitLab pipelines;
- cleanup of superseded namespaces for the same branch or merge request;
- Slack notifications for configured status changes and delete events;
- Prometheus metrics for namespace status, namespace check results, and
  namespace deletions.

## Configuration

Runtime configuration is provided through the Helm chart in
`charts/ska-ser-namespace-manager`. The main configuration blocks are:

- `api.config`: API ports, TLS material, People database settings, and metrics
  settings.
- `collectController.config`: namespace matchers, TTLs, settling and grace
  periods, Prometheus settings, optional GitLab checks, heartbeat, and leader
  election.
- `actionController.config`: namespace matchers, per-status delete and
  notification behavior, Slack token, and leader election.

The default values manage `ci-.*` namespaces and enable Prometheus metrics. The
cancelled and superseded checks are configurable per namespace matcher.

The People database is optional. Environments that do not require it can set
`api.config.people_database.enabled: false`, in which case `spreadsheet_id` and
`credentials` may be omitted — the API still starts and passes its readiness
probe, and `GET /api/people` responds with `not found`. When
`enabled: true` (the default), `spreadsheet_id` and credentials must be provided.

### Layered configuration via VaultStaticSecret

Each component reads every YAML file found in `CONFIG_PATH` when it points at a
directory — which is what the chart mounts (`/etc/config`; the built-in default
is the single file `/etc/config/config.yml`). Files are read in alphabetical
order and deep-merged: later filenames override
earlier ones, nested dictionaries merge key-by-key, and lists are replaced
wholesale. A `null` value in an overlay leaves the base value untouched. The
chart-managed base secret writes its content to `00-base.yml` so any
user-supplied overlay sorts after it and wins on conflicts.

To layer sensitive fields (e.g. `collectController.config.gitlab.private_token`
or `api.config.people_database.credentials.private_key`) without storing them
in Helm values, declare a `VaultStaticSecret` via `extraDeploy` and project the
resulting secret into the component's config directory with
`<component>.extraConfigSecrets`:

```yaml
extraDeploy:
  - apiVersion: secrets.hashicorp.com/v1beta1
    kind: VaultStaticSecret
    metadata:
      name: '{{ template "ska-ser-namespace-manager.collect-controller.name" . }}-vault'
      namespace: '{{ template "ska-ser-namespace-manager.namespace" . }}'
    spec:
      mount: aws-eu-west-2
      type: kv-v2
      path: staging/ska-ser-namespace-manager
      refreshAfter: 60s
      # Roll the workload when the secret rotates — VSO updates the projected
      # volume in place, but the running process keeps the cached config until
      # restart.
      rolloutRestartTargets:
        - kind: StatefulSet
          name: '{{ template "ska-ser-namespace-manager.collect-controller.name" . }}'
      destination:
        create: true
        name: '{{ template "ska-ser-namespace-manager.collect-controller.name" . }}-vault'
        transformation:
          excludeRaw: true

collectController:
  extraConfigSecrets:
    - name: '{{ template "ska-ser-namespace-manager.collect-controller.name" . }}-vault'
      items:
        # The key in the Vault payload becomes the file name in /etc/config.
        # Pick a path that sorts after `00-base.yml` so the overlay wins.
        - key: gitlab.yml
          path: 50-gitlab.yml
```

The Vault payload's `gitlab.yml` key should contain a YAML fragment matching
the live config shape, e.g.:

```yaml
gitlab:
  private_token: glpat-xxxxxxxxxxxxxxxxxxxx
```

The same pattern applies to `api.extraConfigSecrets` and
`actionController.extraConfigSecrets`.

## Development

Clone the repository and initialise the shared tooling submodule:

```bash
git clone git@gitlab.com:ska-telescope/ska-ser-namespace-manager.git
cd ska-ser-namespace-manager
git submodule update --init --recursive
```

Use Python 3.10. Dependencies are managed with `uv`, and the make targets run
inside that environment already:

```bash
uv sync
make python-format
make python-lint
make python-test
```

To install the chart into a local Kubernetes environment:

```bash
make k8s-install-chart
```

If deploying to the
[SDI CI/CD minikube cluster](https://gitlab.com/ska-telescope/sdi/ska-cicd-deploy-minikube),
build a local image first:

```bash
make oci-build-all CAR_OCI_REGISTRY_HOST=localhost:5000
```

Then set the registry to `<local ip>:5000` where relevant in your values file.

For local secrets, create
`charts/ska-ser-namespace-manager/environments/local.yml` using this shape:

```yaml
image:
  repository: registry.gitlab.com/ska-telescope/ska-ser-namespace-manager/ska-ser-namespace-manager
  pullPolicy: IfNotPresent
  tag: <local image tag>

api:
  pki:
    createSelfSignedCert: true
  config:
    people_database:
      spreadsheet_id: <people database spreadsheet id>
      spreadsheet_range: "System Team API!A2:Z1001"
      credentials: <decoded people_database_credentials value>

collectController:
  config:
    namespaces:
      - names:
          - ci-.*
        ttl: 2m

actionController:
  config:
    namespaces:
      - names:
          - ci-.*
```

Populate `api.config.people_database.credentials` from the
`people_database_credentials` secret for the local namespace-manager
environment. Deploy with the local environment values using:

```bash
poetry run make k8s-install-chart ENVIRONMENT=local
```
