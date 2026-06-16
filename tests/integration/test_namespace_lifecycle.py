"""
End-to-end lifecycle tests for ska-ser-namespace-manager.

Each test creates one or more namespaces under the prefixed pattern,
optionally provisions workloads, then waits for the manager to drive
those namespaces to the expected status (annotation + Prometheus metric).
"""

from __future__ import annotations

import time

from ska_ser_namespace_manager.core.types import CicdLabels
from tests.integration.utils import (
    Clients,
    MetricsClient,
    build_deployment,
    get_cicd_labels,
    get_namespace,
    wait_for_deletion,
    wait_for_metric,
    wait_for_status,
)


def test_ok_namespace_stays_ok(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """Healthy deployment → ``ok`` status, namespace not deleted."""
    labels = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: None,
            CicdLabels.PIPELINE_ID.value: None,
        }
    )
    name = namespace_factory("ok", labels=labels)

    k8s_clients.apps.create_namespaced_deployment(
        namespace=name,
        body=build_deployment(
            "ok-sleep",
            image="busybox",
            command=["sh", "-c", "sleep 3600"],
        ),
    )

    wait_for_status(k8s_clients.core, name, "ok")
    assert get_namespace(k8s_clients.core, name) is not None
    wait_for_metric(
        lambda: metrics_client.get_status(name) == 0,
        f"ok status metric for {name}",
    )


def test_stale_namespace_is_deleted(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """Empty namespace older than the configured TTL is deleted as stale."""
    labels = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: None,
            CicdLabels.PIPELINE_ID.value: None,
        }
    )
    before = metrics_client.get_delete_total("stale")
    name = namespace_factory("stale", labels=labels)

    wait_for_status(k8s_clients.core, name, "stale")
    wait_for_deletion(k8s_clients.core, name)
    wait_for_metric(
        lambda: metrics_client.get_delete_total("stale") > before,
        "stale delete metric increased",
    )


def test_failing_namespace_is_deleted(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """Unsatisfiable deployment drives the namespace to FAILED + delete."""
    labels = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: None,
            CicdLabels.PIPELINE_ID.value: None,
        }
    )
    before = metrics_client.get_delete_total("failed")
    name = namespace_factory("fail", labels=labels)

    k8s_clients.apps.create_namespaced_deployment(
        namespace=name,
        body=build_deployment(
            "fail-deploy",
            image="busybox",
            command=["sh", "-c", "sleep 3600"],
            node_selector={"nstest-nonexistent": "true"},
        ),
    )

    wait_for_status(k8s_clients.core, name, "failing")
    wait_for_status(k8s_clients.core, name, "failed")
    wait_for_deletion(k8s_clients.core, name, timeout=120)
    wait_for_metric(
        lambda: metrics_client.get_delete_total("failed") > before,
        "failed delete metric increased",
    )


def test_failing_namespace_recovers_to_ok(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """
    Once the failing deployment is removed (before FAILED triggers delete),
    the namespace recovers to ``ok`` and survives.
    """
    labels = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: None,
            CicdLabels.PIPELINE_ID.value: None,
        }
    )
    name = namespace_factory("recover", labels=labels)
    deployment_name = "recover-deploy"

    k8s_clients.apps.create_namespaced_deployment(
        namespace=name,
        body=build_deployment(
            deployment_name,
            image="busybox",
            command=["sh", "-c", "sleep 3600"],
            node_selector={"nstest-nonexistent": "true"},
        ),
    )

    wait_for_status(k8s_clients.core, name, "unstable")
    wait_for_status(k8s_clients.core, name, "failing")
    k8s_clients.apps.delete_namespaced_deployment(
        deployment_name, namespace=name, grace_period_seconds=0
    )
    wait_for_status(k8s_clients.core, name, "ok")
    assert get_namespace(k8s_clients.core, name) is not None
    wait_for_metric(
        lambda: metrics_client.get_status(name) == 0,
        f"ok status metric for {name}",
    )


def test_cancelled_namespace_404(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """Non-existent GitLab project/pipeline → CANCELLED → deletion."""
    labels = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: "999999999",
            CicdLabels.PIPELINE_ID.value: "999999999",
        }
    )
    before = metrics_client.get_delete_total("cancelled")
    name = namespace_factory("cancel", labels=labels)

    wait_for_status(k8s_clients.core, name, "cancelled")
    wait_for_deletion(k8s_clients.core, name)
    wait_for_metric(
        lambda: metrics_client.get_delete_total("cancelled") > before,
        "cancelled delete metric increased",
    )


def test_superseded_by_mrid(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """Older jobId is SUPERSEDED when grouped by (projectId, mrId, job)."""
    common = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: "11111",
            CicdLabels.PIPELINE_ID.value: None,
            CicdLabels.BRANCH.value: None,
            CicdLabels.MR_ID.value: "42",
            CicdLabels.JOB.value: "deploy",
        }
    )
    before = metrics_client.get_delete_total("superseded")

    older = namespace_factory(
        "sup-mr-a",
        labels={**common, CicdLabels.JOB_ID.value: "1"},
    )
    time.sleep(2)
    newer = namespace_factory(
        "sup-mr-b",
        labels={**common, CicdLabels.JOB_ID.value: "2"},
    )

    wait_for_status(k8s_clients.core, older, "superseded")
    wait_for_deletion(k8s_clients.core, older)
    assert get_namespace(k8s_clients.core, newer) is not None
    wait_for_metric(
        lambda: metrics_client.get_delete_total("superseded") > before,
        "superseded delete metric increased",
    )


def test_superseded_multi_namespace_per_job(
    namespace_factory,
    k8s_clients: Clients,
    metrics_client: MetricsClient,
):
    """
    Each ``jobId`` deploys two namespaces. The older jobId's namespaces
    are both superseded; the newer jobId's namespaces both survive.
    Same-jobId siblings do not supersede each other.
    """
    common = get_cicd_labels(
        **{
            CicdLabels.PROJECT_ID.value: "22222",
            CicdLabels.PIPELINE_ID.value: None,
            CicdLabels.BRANCH.value: "main",
            CicdLabels.JOB.value: "multi-deploy",
        }
    )
    before = metrics_client.get_delete_total("superseded")

    older_a = namespace_factory(
        "sup-j1-a", labels={**common, CicdLabels.JOB_ID.value: "1"}
    )
    older_b = namespace_factory(
        "sup-j1-b", labels={**common, CicdLabels.JOB_ID.value: "1"}
    )
    time.sleep(2)
    newer_a = namespace_factory(
        "sup-j2-a", labels={**common, CicdLabels.JOB_ID.value: "2"}
    )
    newer_b = namespace_factory(
        "sup-j2-b", labels={**common, CicdLabels.JOB_ID.value: "2"}
    )

    wait_for_status(k8s_clients.core, older_a, "superseded")
    wait_for_status(k8s_clients.core, older_b, "superseded")
    wait_for_deletion(k8s_clients.core, older_a)
    wait_for_deletion(k8s_clients.core, older_b)
    assert get_namespace(k8s_clients.core, newer_a) is not None
    assert get_namespace(k8s_clients.core, newer_b) is not None
    wait_for_metric(
        lambda: metrics_client.get_delete_total("superseded") >= before + 2,
        "superseded delete metric increased by >=2",
    )
