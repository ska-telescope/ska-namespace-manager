# SKA Namespace Manager

SKA Namespace Manager manages CI/CD namespaces in a Kubernetes cluster. It
keeps temporary environments visible, applies lifecycle policies, exports
namespace health metrics, and deletes namespaces that are stale, failed,
cancelled, or superseded.

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
flowchart TD
    ns["Kubernetes namespaces<br/>labels and annotations"]
    k8s["Kubernetes API"]
    prom["Prometheus alerts"]
    gitlab["GitLab pipeline API"]
    people["People database"]
    metrics["Shared metrics registry<br/>Prometheus text files"]
    slack["Slack"]

    subgraph app["SKA Namespace Manager"]
        api["FastAPI service<br/>/health, /api/people, /api/metrics"]
        collect["Collect controller<br/>manage, check, annotate"]
        action["Action controller<br/>notify and delete"]
    end

    collect --> k8s
    k8s --> ns
    ns --> collect
    prom --> collect
    gitlab --> collect
    collect --> ns
    collect --> metrics

    action --> k8s
    ns --> action
    action --> slack
    action --> metrics

    api --> people
    api --> metrics
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
    [*] --> unknown: namespace matches config
    unknown --> ok: no stale or failing condition
    unknown --> unstable: failing resources detected
    unknown --> cancelled: originating pipeline cancelled or missing
    unknown --> superseded: newer CI deployment found

    ok --> unstable: Prometheus or resource check fails
    ok --> stale: TTL elapsed
    ok --> cancelled: originating pipeline cancelled or missing
    ok --> superseded: newer CI deployment found

    unstable --> ok: alerts clear
    unstable --> failing: settling period elapsed
    unstable --> stale: TTL elapsed
    unstable --> cancelled: originating pipeline cancelled or missing
    unstable --> superseded: newer CI deployment found

    failing --> ok: alerts clear
    failing --> failed: grace period elapsed
    failing --> stale: TTL elapsed
    failing --> cancelled: originating pipeline cancelled or missing
    failing --> superseded: newer CI deployment found

    stale --> deleted: action controller deletes
    failed --> deleted: action controller deletes
    cancelled --> deleted: action controller deletes
    superseded --> deleted: action controller deletes
    deleted --> [*]
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

### Layered configuration via VaultStaticSecret

Each component reads every YAML file found in `CONFIG_PATH` (`/etc/config` by
default), sorted alphabetically, and deep-merges them: later filenames override
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

Use Python 3.10 and the repository Poetry environment. The standard local
checks are:

```bash
poetry run make python-format
poetry run make python-lint
poetry run make python-test
```

To install the chart into a local Kubernetes environment:

```bash
poetry run make k8s-install-chart
```

If deploying to the
[SDI CI/CD minikube cluster](https://gitlab.com/ska-telescope/sdi/ska-cicd-deploy-minikube),
build a local image first:

```bash
poetry run make oci-build-all CAR_OCI_REGISTRY_HOST=localhost:5000
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
      spreadsheet_id: 1WekvYFWkPRiWoB2yzp1BrMRwwu0fRqf20d7XbqO6OJg
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
