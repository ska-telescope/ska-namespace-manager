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
    collector.namespace = "ci-test"
    collector.prometheus_config = SimpleNamespace(datacentre=datacentre)
    collector.namespace_config = SimpleNamespace(ttl=None)
    collector.check_stale = MagicMock(return_value=(False, {}))
    collector.check_failure = MagicMock(
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
    alerts = [
        make_alert("ci-test", "stfc-techops"),
        make_alert("ci-test", "other-site"),
        make_alert("other-namespace", "stfc-techops"),
    ]

    collector.evaluate_namespace_health(namespace, alerts)

    collector.check_failure.assert_called_once_with(
        namespace, [make_alert("ci-test", "stfc-techops")]
    )


def test_evaluate_namespace_health_ignores_different_datacentre():
    """Alerts from a different datacentre should be ignored."""
    collector = make_collector(datacentre="stfc-techops")
    namespace = make_namespace()
    alerts = [make_alert("ci-test", "other-site")]

    collector.evaluate_namespace_health(namespace, alerts)

    collector.check_failure.assert_called_once_with(namespace, [])


def test_evaluate_namespace_health_ignores_missing_datacentre():
    """Alerts without a datacentre label should not match configured ones."""
    collector = make_collector(datacentre="stfc-techops")
    namespace = make_namespace()
    alerts = [make_alert("ci-test")]

    collector.evaluate_namespace_health(namespace, alerts)

    collector.check_failure.assert_called_once_with(namespace, [])


def test_evaluate_namespace_health_without_datacentre():
    """
    Namespace-only matching should remain when no datacentre is configured.
    """
    collector = make_collector()
    namespace = make_namespace()
    alerts = [
        make_alert("ci-test"),
        make_alert("ci-test", "other-site"),
        make_alert("other-namespace", "stfc-techops"),
    ]

    collector.evaluate_namespace_health(namespace, alerts)

    collector.check_failure.assert_called_once_with(
        namespace,
        [make_alert("ci-test"), make_alert("ci-test", "other-site")],
    )
