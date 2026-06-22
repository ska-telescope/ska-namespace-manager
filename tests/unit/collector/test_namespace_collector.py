"""Tests for namespace collector alert filtering behavior."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ska_ser_namespace_manager.collector.gitlab_pipeline_client import (
    CANCELED_STATUS,
    NOT_FOUND_STATUS,
)
from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.core.types import (
    CicdLabels,
    NamespaceAnnotations,
    NamespaceStatus,
)


def make_namespace(name="ci-test"):
    """Build a minimal namespace object for collector tests."""
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            creation_timestamp=datetime.now(timezone.utc),
            labels={},
            annotations={},
        )
    )


def make_collector(datacentre=None):
    """Build a namespace collector without running the full initializer."""
    collector = NamespaceCollector.__new__(NamespaceCollector)
    collector.prometheus_config = SimpleNamespace(datacentre=datacentre)
    collector.gitlab_config = SimpleNamespace(enabled=False)
    collector._check_stale = MagicMock(return_value=(False, {}))
    collector._check_failure = MagicMock(
        return_value=(
            "ok",
            {NamespaceAnnotations.FAILING_RESOURCES.value: "[]"},
        )
    )
    return collector


def make_checks(cancelled=False, superseded=False):
    """Build check options for collector tests."""
    return SimpleNamespace(cancelled=cancelled, superseded=superseded)


def make_alert(namespace, datacentre=None):
    """Build a minimal alert payload for filtering tests."""
    labels = {
        "namespace": namespace,
        "alertname": "DeploymentReplicasMismatch",
    }
    if datacentre is not None:
        labels["datacentre"] = datacentre

    return {"labels": labels, "annotations": {}}


def test_evaluate_namespace_health_filters_matching_datacentre():
    """Matching namespace and datacentre alerts should be considered."""
    collector = make_collector(datacentre="stfc-techops")
    namespace = make_namespace()
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks())
    alerts = [
        make_alert("ci-test", "stfc-techops"),
        make_alert("ci-test", "other-site"),
        make_alert("other-namespace", "stfc-techops"),
    ]

    collector._evaluate_namespace_health("ci-test", namespace, namespace_config, alerts)

    collector._check_failure.assert_called_once_with(
        "ci-test",
        namespace_config,
        namespace,
        [make_alert("ci-test", "stfc-techops")],
    )


def test_evaluate_namespace_health_ignores_different_datacentre():
    """Alerts from a different datacentre should be ignored."""
    collector = make_collector(datacentre="stfc-techops")
    namespace = make_namespace()
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks())
    alerts = [make_alert("ci-test", "other-site")]

    collector._evaluate_namespace_health("ci-test", namespace, namespace_config, alerts)

    collector._check_failure.assert_called_once_with(
        "ci-test", namespace_config, namespace, []
    )


def test_evaluate_namespace_health_ignores_missing_datacentre():
    """Alerts without a datacentre label should not match configured ones."""
    collector = make_collector(datacentre="stfc-techops")
    namespace = make_namespace()
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks())
    alerts = [make_alert("ci-test")]

    collector._evaluate_namespace_health("ci-test", namespace, namespace_config, alerts)

    collector._check_failure.assert_called_once_with(
        "ci-test", namespace_config, namespace, []
    )


def test_evaluate_namespace_health_without_datacentre():
    """
    Namespace-only matching should remain when no datacentre is configured.
    """
    collector = make_collector()
    namespace = make_namespace()
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks())
    alerts = [
        make_alert("ci-test"),
        make_alert("ci-test", "other-site"),
        make_alert("other-namespace", "stfc-techops"),
    ]

    collector._evaluate_namespace_health("ci-test", namespace, namespace_config, alerts)

    collector._check_failure.assert_called_once_with(
        "ci-test",
        namespace_config,
        namespace,
        [make_alert("ci-test"), make_alert("ci-test", "other-site")],
    )


def test_check_namespace_resolves_config_per_invocation():
    """Each namespace check should use its own matched namespace config."""
    collector = NamespaceCollector.__new__(NamespaceCollector)
    collector.prometheus_config = SimpleNamespace(enabled=False)
    collector.gitlab_config = SimpleNamespace(enabled=False)
    collector.get_namespace_config = MagicMock(
        side_effect=[
            SimpleNamespace(ttl="config-a"),
            SimpleNamespace(ttl="config-b"),
        ]
    )
    collector._evaluate_namespace_health = MagicMock(
        side_effect=[
            ("ok", {NamespaceAnnotations.FAILING_RESOURCES.value: "[]"}),
            ("ok", {NamespaceAnnotations.FAILING_RESOURCES.value: "[]"}),
        ]
    )
    collector._set_status = MagicMock()
    namespace_a = make_namespace("ci-a")
    namespace_b = make_namespace("ci-b")

    collector.check_namespace("ci-a", namespace_a)
    collector.check_namespace("ci-b", namespace_b)

    assert collector.get_namespace_config.call_args_list[0].args == (namespace_a,)
    assert collector.get_namespace_config.call_args_list[1].args == (namespace_b,)
    assert collector._evaluate_namespace_health.call_args_list[0].args[2].ttl
    assert collector._evaluate_namespace_health.call_args_list[1].args[2].ttl
    assert (
        collector._evaluate_namespace_health.call_args_list[0].args[2].ttl == "config-a"
    )
    assert (
        collector._evaluate_namespace_health.call_args_list[1].args[2].ttl == "config-b"
    )


def make_gitlab_collector(status="success"):
    """Build a collector with GitLab lookup enabled."""
    collector = make_collector()
    collector.gitlab_config = SimpleNamespace(enabled=True)
    collector.gitlab_pipeline_client = MagicMock()
    collector.gitlab_pipeline_client.get_pipeline_status = MagicMock(
        return_value=status
    )
    return collector


def make_pipeline_namespace(status=NamespaceStatus.UNKNOWN.value):
    """Build a namespace with CI pipeline labels."""
    namespace = make_namespace()
    namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: status,
    }
    namespace.metadata.labels = {
        CicdLabels.PROJECT_ID.value: "123",
        CicdLabels.PIPELINE_ID.value: "456",
    }
    return namespace


@pytest.mark.parametrize("pipeline_status", [CANCELED_STATUS, NOT_FOUND_STATUS])
def test_check_cancelled_pipeline_marks_cancelled(pipeline_status):
    """Cancelled or missing GitLab pipelines should cancel namespaces."""
    collector = make_gitlab_collector(status=pipeline_status)
    namespace = make_pipeline_namespace()

    assert collector._check_cancelled_pipeline(namespace) == NamespaceStatus.CANCELLED
    collector.gitlab_pipeline_client.get_pipeline_status.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        "123", "456"
    )


def test_check_cancelled_pipeline_ignores_active_pipeline():
    """Active GitLab pipelines should not cancel namespaces."""
    collector = make_gitlab_collector(status="running")
    namespace = make_pipeline_namespace()

    assert collector._check_cancelled_pipeline(namespace) is None


def test_check_cancelled_pipeline_ignores_missing_labels():
    """Missing pipeline labels should skip GitLab lookups."""
    collector = make_gitlab_collector(status=CANCELED_STATUS)
    namespace = make_namespace()

    assert collector._check_cancelled_pipeline(namespace) is None
    collector.gitlab_pipeline_client.get_pipeline_status.assert_not_called()


def test_evaluate_namespace_health_skips_cancelled_pipeline_by_default():
    """GitLab cancellation lookup should be opt-in per namespace config."""
    collector = make_gitlab_collector(status=CANCELED_STATUS)
    namespace = make_pipeline_namespace()
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks())

    status, annotations = collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts=[]
    )

    assert status == "ok"
    assert annotations == {
        NamespaceAnnotations.FAILING_RESOURCES.value: "[]",
    }
    collector.gitlab_pipeline_client.get_pipeline_status.assert_not_called()
    collector._check_failure.assert_called_once_with(
        "ci-test", namespace_config, namespace, []
    )


@pytest.mark.parametrize("pipeline_status", [CANCELED_STATUS, NOT_FOUND_STATUS])
def test_evaluate_namespace_health_checks_cancelled_when_enabled(
    pipeline_status,
):
    """Opted-in namespaces should check GitLab cancellation status."""
    collector = make_gitlab_collector(status=pipeline_status)
    namespace = make_pipeline_namespace()
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks(cancelled=True))

    status, annotations = collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts=[]
    )

    assert status == NamespaceStatus.CANCELLED
    assert annotations == namespace.metadata.annotations
    get_pipeline_status = collector.gitlab_pipeline_client.get_pipeline_status
    get_pipeline_status.assert_called_once_with("123", "456")
    collector._check_stale.assert_not_called()
    collector._check_failure.assert_not_called()


def test_evaluate_namespace_health_preserves_cancelled_after_gitlab_failure():
    """Already cancelled namespaces should stay cancelled on lookup failure."""
    collector = make_gitlab_collector(status=None)
    namespace = make_pipeline_namespace(status=NamespaceStatus.CANCELLED.value)
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks(cancelled=True))

    status, annotations = collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts=[]
    )

    assert status == NamespaceStatus.CANCELLED
    assert annotations == namespace.metadata.annotations
    collector.gitlab_pipeline_client.get_pipeline_status.assert_not_called()
    collector._check_stale.assert_not_called()
    collector._check_failure.assert_not_called()


def test_evaluate_namespace_health_preserves_superseded():
    """Already superseded namespaces should stay superseded."""
    collector = make_gitlab_collector(status=CANCELED_STATUS)
    namespace = make_pipeline_namespace(status=NamespaceStatus.SUPERSEDED.value)
    namespace_config = SimpleNamespace(ttl=None, checks=make_checks(cancelled=True))

    status, annotations = collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts=[]
    )

    assert status == NamespaceStatus.SUPERSEDED
    assert annotations == namespace.metadata.annotations
    collector.gitlab_pipeline_client.get_pipeline_status.assert_not_called()
    collector._check_stale.assert_not_called()
    collector._check_failure.assert_not_called()
