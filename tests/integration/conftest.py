"""
Pytest fixtures for the namespace-manager integration tests.

Tests run on the GitLab runner (not in-cluster) and drive a real deployed
ska-ser-namespace-manager via the runner's kubeconfig. The deploy
namespace is resolved from ``NSTEST_MANAGER_NAMESPACE`` (preferred) or
``KUBE_NAMESPACE`` (set by the SKA k8s make targets) — never via a
cluster-wide search, so we cannot accidentally hit a stable deployment.

Pure helpers (polling, label builders, metrics scraping) live in
``tests.integration.utils``; this module only wires fixtures.
"""

from __future__ import annotations

import logging
import os
from typing import Callable, Dict, Iterator, List, Optional

import pytest
from kubernetes import client
from kubernetes.client.rest import ApiException

from tests.integration.utils import (
    Clients,
    MetricsClient,
    PeopleIdentity,
    delete_namespace,
    list_test_namespaces,
    load_kube_config,
    new_namespace_name,
    wait_for,
)

logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def k8s_clients() -> Clients:
    load_kube_config()
    return Clients(core=client.CoreV1Api(), apps=client.AppsV1Api())


@pytest.fixture(scope="session")
def manager_namespace() -> str:
    """
    Resolve the namespace where ska-ser-namespace-manager is installed.

    Strategy (no cluster-wide discovery — avoids ever talking to a
    stable/production deployment by accident):
      1. ``NSTEST_MANAGER_NAMESPACE`` env var if set,
      2. otherwise ``KUBE_NAMESPACE`` (set by the SKA k8s make targets
         to the namespace the chart was just deployed into).

    Skips the whole suite if neither is set.
    """
    namespace = os.environ.get("NSTEST_MANAGER_NAMESPACE") or os.environ.get(
        "KUBE_NAMESPACE"
    )
    if not namespace:
        pytest.skip(
            "Neither NSTEST_MANAGER_NAMESPACE nor KUBE_NAMESPACE is set; "
            "cannot locate the deployed namespace manager."
        )

    return namespace


@pytest.fixture(scope="session")
def namespace_prefix() -> str:
    """
    Resolve the namespace prefix to use.
    """
    return os.environ.get("NSTEST_NAMESPACE_PREFIX", "nscicd-test-")


@pytest.fixture(scope="session")
def api_service(k8s_clients: Clients, manager_namespace: str) -> client.V1Service:
    """Return the manager's api Service object."""
    try:
        services = k8s_clients.core.list_namespaced_service(
            namespace=manager_namespace,
            label_selector="app.kubernetes.io/component=api",
        )
    except Exception as exc:  # pylint: disable=broad-except
        pytest.skip(f"Cluster not reachable: {exc}")

    if not services.items:
        pytest.skip(f"No API service found in namespace '{manager_namespace}'")

    return services.items[0]


@pytest.fixture(scope="session", autouse=True)
def session_cleanup(
    k8s_clients: Clients,
    manager_namespace: str,
    namespace_prefix,
) -> Iterator[None]:
    """Wipe leftover cicd test namespaces before the suite (best-effort).

    Depends on ``manager_namespace`` so that the session-level skip for
    a missing ``KUBE_NAMESPACE``/``NSTEST_MANAGER_NAMESPACE`` fires
    before we try to talk to the cluster.
    """
    del manager_namespace  # ordering dependency only
    try:
        leftovers = list_test_namespaces(namespace_prefix, k8s_clients.core)
    except Exception as exc:  # pylint: disable=broad-except
        pytest.skip(f"Cluster not reachable: {exc}")

    if leftovers:
        logger.info(
            "Cleaning %d leftover nstest namespace(s) before suite: %s",
            len(leftovers),
            leftovers,
        )
        for name in leftovers:
            delete_namespace(k8s_clients.core, name)

    yield


@pytest.fixture
def namespace_factory(
    k8s_clients: Clients,
    namespace_prefix: str,
) -> Iterator[Callable[..., str]]:
    """
    Factory fixture that creates prefixed namespaces
    with CICD labels and tracks them for teardown.
    """
    created: List[str] = []

    def _make(
        scenario: str,
        *,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
    ) -> str:
        name = new_namespace_name(namespace_prefix, scenario)
        body = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=name,
                labels=labels or {},
                annotations=annotations or {},
            )
        )
        k8s_clients.core.create_namespace(body)
        created.append(name)
        logger.info("Created namespace %s", name)

        return name

    yield _make

    for name in created:
        delete_namespace(k8s_clients.core, name)


@pytest.fixture(scope="session")
def metrics_client(
    k8s_clients: Clients,
    manager_namespace: str,
    api_service: client.V1Service,
) -> MetricsClient:
    return MetricsClient(k8s_clients.core, manager_namespace, api_service)


@pytest.fixture(scope="session", autouse=True)
def api_reachable(metrics_client: MetricsClient) -> None:
    """Skip the suite if the manager's metrics endpoint is unreachable."""
    try:
        wait_for(
            lambda: bool(list(metrics_client.families())),
            timeout=30,
            interval=3,
            description="manager /api/metrics reachable",
        )
    except (AssertionError, ApiException) as exc:
        pytest.skip(
            f"Manager API endpoint not reachable, skipping integration suite: {exc}"
        )


@pytest.fixture(scope="session")
def people_identity() -> PeopleIdentity:
    """Identity for the people-API test; skip if any env var is unset."""
    keys = {
        "gitlab_handle": "NSTEST_AUTHOR_GITLAB_HANDLE",
        "author_id": "NSTEST_AUTHOR_ID",
        "email": "NSTEST_AUTHOR_EMAIL",
        "team": "NSTEST_EXPECTED_TEAM",
        "slack_id": "NSTEST_EXPECTED_SLACK_ID",
    }
    resolved = {field: os.environ.get(env) for field, env in keys.items()}
    missing = [env for field, env in keys.items() if not resolved[field]]
    if missing:
        pytest.skip("People API identity env vars not set: " + ", ".join(missing))

    return PeopleIdentity(**resolved)
