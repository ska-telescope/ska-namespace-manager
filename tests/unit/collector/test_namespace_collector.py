"""Tests for namespace collector alert filtering behavior."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.core.types import NamespaceAnnotations


def make_namespace(name="ci-test"):
    """Build a minimal namespace object for collector tests."""
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            creation_timestamp=datetime.now(timezone.utc),
            annotations={},
        )
    )


def make_collector(datacentre=None):
    """Build a namespace collector without running the full initializer."""
    collector = NamespaceCollector.__new__(NamespaceCollector)
    collector.prometheus_config = SimpleNamespace(datacentre=datacentre)
    collector._check_stale = MagicMock(return_value=(False, {}))
    collector._check_failure = MagicMock(
        return_value=(
            "ok",
            {NamespaceAnnotations.FAILING_RESOURCES.value: "[]"},
        )
    )
    return collector


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
    namespace_config = SimpleNamespace(ttl=None)
    alerts = [
        make_alert("ci-test", "stfc-techops"),
        make_alert("ci-test", "other-site"),
        make_alert("other-namespace", "stfc-techops"),
    ]

    collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts
    )

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
    namespace_config = SimpleNamespace(ttl=None)
    alerts = [make_alert("ci-test", "other-site")]

    collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts
    )

    collector._check_failure.assert_called_once_with(
        "ci-test", namespace_config, namespace, []
    )


def test__evaluate_namespace_health_ignores_missing_datacentre():
    """Alerts without a datacentre label should not match configured ones."""
    collector = make_collector(datacentre="stfc-techops")
    namespace = make_namespace()
    namespace_config = SimpleNamespace(ttl=None)
    alerts = [make_alert("ci-test")]

    collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts
    )

    collector._check_failure.assert_called_once_with(
        "ci-test", namespace_config, namespace, []
    )


def test_evaluate_namespace_health_without_datacentre():
    """
    Namespace-only matching should remain when no datacentre is configured.
    """
    collector = make_collector()
    namespace = make_namespace()
    namespace_config = SimpleNamespace(ttl=None)
    alerts = [
        make_alert("ci-test"),
        make_alert("ci-test", "other-site"),
        make_alert("other-namespace", "stfc-techops"),
    ]

    collector._evaluate_namespace_health(
        "ci-test", namespace, namespace_config, alerts
    )

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

    assert collector.get_namespace_config.call_args_list[0].args == (
        namespace_a,
    )
    assert collector.get_namespace_config.call_args_list[1].args == (
        namespace_b,
    )
    assert collector._evaluate_namespace_health.call_args_list[0].args[2].ttl
    assert collector._evaluate_namespace_health.call_args_list[1].args[2].ttl
    assert (
        collector._evaluate_namespace_health.call_args_list[0].args[2].ttl
        == "config-a"
    )
    assert (
        collector._evaluate_namespace_health.call_args_list[1].args[2].ttl
        == "config-b"
    )
