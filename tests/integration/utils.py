"""
Helpers shared by the namespace-manager integration tests.

All non-fixture code lives here so that ``conftest.py`` only contains
pytest fixtures. Anything that needs to be reused from test modules
(constants, dataclasses, polling helpers, the metrics scraper, etc.)
should be imported from ``tests.integration.utils``.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Tuple

from kubernetes import client, config
from kubernetes.client.rest import ApiException
from prometheus_client import Metric
from prometheus_client.parser import text_string_to_metric_families

from ska_ser_namespace_manager.core.types import (
    CicdLabels,
    NamespaceAnnotations,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT = 120
DEFAULT_INTERVAL = 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Clients:
    """Kubernetes API client bundle used by every fixture and helper."""

    core: client.CoreV1Api
    apps: client.AppsV1Api


@dataclass(frozen=True)
class PeopleIdentity:
    """Identity for the people-API test (sourced from env vars)."""

    gitlab_handle: str
    author_id: str
    email: str
    team: str
    slack_id: str


# ---------------------------------------------------------------------------
# Cluster connection
# ---------------------------------------------------------------------------


def load_kube_config() -> None:
    """Load kubeconfig, preferring the runner's KUBECONFIG over in-cluster."""
    try:
        config.load_kube_config()
        logger.info("Loaded kubeconfig from runner environment")
        return
    except config.ConfigException:
        pass

    config.load_incluster_config()
    logger.info("Loaded in-cluster kubeconfig")


# ---------------------------------------------------------------------------
# Polling
# ---------------------------------------------------------------------------


def wait_for(
    predicate: Callable[[], object],
    *,
    timeout: float = DEFAULT_TIMEOUT,
    interval: float = DEFAULT_INTERVAL,
    description: str = "predicate",
):
    """
    Poll until ``predicate()`` returns a truthy value or timeout elapses.

    Returns whatever the predicate last returned (truthy on success).
    Raises ``AssertionError`` on timeout, embedding the last value for
    debugging.
    """
    deadline = time.monotonic() + timeout
    last_value = None
    while time.monotonic() < deadline:
        last_value = predicate()
        if last_value:
            return last_value

        time.sleep(interval)

    raise AssertionError(
        f"Timed out after {timeout}s waiting for {description}; "
        f"last value: {last_value!r}"
    )


# ---------------------------------------------------------------------------
# Label and name builders
# ---------------------------------------------------------------------------


def get_cicd_labels(**overrides: Optional[str]) -> Dict[str, str]:
    """
    Return a dict of CICD labels with sensible synthetic defaults.

    Pass ``key=None`` to *remove* a default (used by the OK test to drop
    ``projectId``/``pipelineId`` so the cancelled check short-circuits).
    """
    defaults: Dict[str, Optional[str]] = {
        CicdLabels.PROJECT_ID.value: "1234567",
        CicdLabels.PROJECT.value: "nstest-project",
        CicdLabels.PIPELINE_ID.value: "9999999",
        CicdLabels.JOB.value: "nstest-job",
        CicdLabels.JOB_ID.value: "1",
        CicdLabels.BRANCH.value: "nstest-branch",
        CicdLabels.AUTHOR.value: "nstest-author",
        CicdLabels.PERMITTED.value: "true",
    }
    defaults.update(overrides)

    return {k: v for k, v in defaults.items() if v is not None}


def new_namespace_name(prefix: str, scenario: str) -> str:
    """Return a fresh, unique prefixed namespace name."""
    return f"{prefix}{scenario}-{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Namespace operations
# ---------------------------------------------------------------------------


def get_namespace(
    core: client.CoreV1Api, name: str
) -> Optional[client.V1Namespace]:
    """Return the namespace object or ``None`` if it does not exist."""
    try:
        return core.read_namespace(name)
    except ApiException as exc:
        if exc.status == 404:
            return None

        raise


def namespace_exists(core: client.CoreV1Api, name: str) -> bool:
    """True if the namespace exists and is not already Terminating."""
    ns = get_namespace(core, name)
    if ns is None:
        return False

    # A namespace marked for deletion still appears but with phase=Terminating.
    return (ns.status.phase if ns.status else None) != "Terminating"


def get_status_annotation(core: client.CoreV1Api, name: str) -> Optional[str]:
    """Return the manager-set status annotation, or None if absent/gone."""
    ns = get_namespace(core, name)
    if ns is None:
        return None

    annotations = (ns.metadata.annotations or {}) if ns.metadata else {}

    return annotations.get(NamespaceAnnotations.STATUS.value)


def delete_namespace(core: client.CoreV1Api, name: str) -> None:
    """Delete a namespace, ignoring 404s and logging other failures."""
    try:
        core.delete_namespace(name, grace_period_seconds=0)
    except ApiException as exc:
        if exc.status != 404:
            logger.warning("Failed to delete namespace %s: %s", name, exc)


def list_test_namespaces(prefix: str, core: client.CoreV1Api) -> List[str]:
    """Return all namespace names that start with the cicd testing prefix."""
    namespaces = core.list_namespace().items
    return [
        ns.metadata.name
        for ns in namespaces
        if (ns.metadata.name or "").startswith(prefix)
    ]


def wait_for_status(
    core: client.CoreV1Api,
    namespace: str,
    status: str,
    **wait_kwargs,
) -> None:
    """Poll the manager status annotation until it equals ``status``."""
    logging.info(
        "Waiting for namespace %s to reach status `%s`", namespace, status
    )
    wait_for(
        lambda: get_status_annotation(core, namespace) == status,
        description=f"namespace {namespace} status == {status}",
        **wait_kwargs,
    )
    logging.info("Namespace %s reached status `%s`", namespace, status)


def wait_for_deletion(
    core: client.CoreV1Api,
    namespace: str,
    **wait_kwargs,
) -> None:
    """Poll the API until the namespace is deleted."""
    logging.info("Waiting for namespace %s to be deleted", namespace)
    wait_for(
        lambda: not namespace_exists(core, namespace),
        description=f"namespace {namespace} deleted",
        **wait_kwargs,
    )
    logging.info("Namespace %s was deleted", namespace)


def wait_for_metric(
    predicate: Callable[[], bool],
    description: str,
    *,
    timeout: float = 30,
    interval: float = 2,
) -> None:
    """Poll a metric-based predicate. The manager scrapes/aggregates on
    its own schedule, so metric reads lag the corresponding K8s state by
    a few seconds — use this (instead of asserting directly) when reading
    counters/gauges from the API.
    """
    logging.info("Waiting for metric: %s", description)
    wait_for(
        predicate,
        description=description,
        timeout=timeout,
        interval=interval,
    )
    logging.info("Metric reached: %s", description)


# ---------------------------------------------------------------------------
# Workload builders
# ---------------------------------------------------------------------------


def build_deployment(
    name: str,
    *,
    image: str,
    command: Optional[List[str]] = None,
    node_selector: Optional[Dict[str, str]] = None,
    replicas: int = 1,
) -> client.V1Deployment:
    """Return a minimal Deployment manifest suitable for integration tests."""
    container = client.V1Container(
        name=name,
        image=image,
        command=command,
        image_pull_policy="IfNotPresent",
    )
    return client.V1Deployment(
        metadata=client.V1ObjectMeta(name=name),
        spec=client.V1DeploymentSpec(
            replicas=replicas,
            selector=client.V1LabelSelector(
                match_labels={"app": name},
            ),
            template=client.V1PodTemplateSpec(
                metadata=client.V1ObjectMeta(labels={"app": name}),
                spec=client.V1PodSpec(
                    containers=[container],
                    node_selector=node_selector,
                    termination_grace_period_seconds=1,
                ),
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Manager API access (service proxy + metrics scraper)
# ---------------------------------------------------------------------------


def service_proxy_name(svc: client.V1Service) -> str:
    """Return the ``scheme:name:port`` ref for kube service proxy calls."""
    port = svc.spec.ports[0]
    scheme = "https" if (port.name or "").lower() == "https" else "http"
    return f"{scheme}:{svc.metadata.name}:{port.port}"


def api_get(
    core: client.CoreV1Api,
    namespace: str,
    service: client.V1Service,
    path: str,
    *,
    query: Optional[Mapping[str, str]] = None,
) -> Tuple[int, str]:
    """
    GET a path on the manager API via the kube-apiserver service proxy.

    The high-level ``connect_get_namespaced_service_proxy_with_path``
    URL-encodes its ``path`` arg, so a ``?`` separator becomes ``%3F``
    and the upstream sees a single literal path with no query string.
    We work around that by calling the underlying ``ApiClient.call_api``
    directly and passing query parameters through ``query_params`` so
    the API server appends them as a proper query string.

    Returns ``(status_code, body_text)``; HTTP errors from the upstream
    are translated into the tuple rather than raised.
    """
    name = service_proxy_name(service)
    resource_path = (
        f"/api/v1/namespaces/{namespace}"
        f"/services/{name}/proxy/{path.lstrip('/')}"
    )
    query_params = [(k, v) for k, v in (query or {}).items() if v is not None]
    try:
        # _preload_content=False bypasses the client's response
        # deserialization, which would otherwise json.loads() the body
        # into a dict and then ``str()`` it (yielding a Python-repr
        # string with single quotes that breaks json.loads downstream).
        response, status, _ = core.api_client.call_api(
            resource_path,
            "GET",
            path_params={},
            query_params=query_params,
            header_params={"Accept": "*/*"},
            auth_settings=["BearerToken"],
            _return_http_data_only=False,
            _preload_content=False,
        )
        body = response.data
        if isinstance(body, bytes):
            body = body.decode("utf-8")

        return status, body
    except ApiException as exc:
        body = exc.body or ""
        if isinstance(body, bytes):
            body = body.decode("utf-8", errors="replace")

        return exc.status, body


def api_get_json(
    core: client.CoreV1Api,
    namespace: str,
    service: client.V1Service,
    path: str,
    *,
    query: Optional[Mapping[str, str]] = None,
) -> Tuple[int, dict]:
    """``api_get`` variant that parses the body as JSON (best-effort)."""
    status, body = api_get(core, namespace, service, path, query=query)
    try:
        return status, json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return status, {"raw": body}


class MetricsClient:
    """Lightweight Prometheus scraper over the kube-apiserver service proxy."""

    def __init__(
        self,
        core: client.CoreV1Api,
        namespace: str,
        service: client.V1Service,
    ):
        self._core = core
        self._namespace = namespace
        self._service = service

    def _fetch(self) -> str:
        status, body = api_get(
            self._core, self._namespace, self._service, "api/metrics"
        )
        if status != 200:
            raise RuntimeError(f"GET api/metrics returned {status}: {body!r}")

        return body

    def families(self) -> Iterable[Metric]:
        """Yield Prometheus metric families parsed from the manager API."""
        return text_string_to_metric_families(self._fetch())

    def get_status(self, namespace: str) -> Optional[float]:
        """Return ``namespace_manager_ns_status`` for the given namespace."""
        for fam in self.families():
            if fam.name != "namespace_manager_ns_status":
                continue

            for sample in fam.samples:
                if sample.labels.get("namespace") == namespace:
                    return sample.value

        return None

    def get_delete_total(self, status: str) -> float:
        """Return summed ``namespace_manager_ns_delete_total`` for a status."""
        total = 0.0
        for fam in self.families():
            if fam.name != "namespace_manager_ns_delete":
                continue

            for sample in fam.samples:
                if sample.labels.get("status") == status:
                    total += sample.value

        return total
