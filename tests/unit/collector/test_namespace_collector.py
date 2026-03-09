"""test_namespace_collector tests namespace collector behavior"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.core.types import (
    NamespaceAnnotations,
    NamespaceStatus,
)


def make_collector() -> NamespaceCollector:
    collector = NamespaceCollector.__new__(NamespaceCollector)
    collector.namespace = "ci-test"
    collector.namespace_config = MagicMock()
    collector.namespace_config.ttl = timedelta(minutes=5)
    collector.namespace_config.settling_period = timedelta(minutes=5)
    collector.namespace_config.grace_period = timedelta(minutes=1)
    collector.prometheus_config = MagicMock()
    collector.prometheus_config.enabled = True
    collector.prometheus_config.url = "http://prometheus"
    collector.prometheus_config.ca = None
    collector.prometheus_config.ca_path = None
    collector.prometheus_config.insecure = True
    collector.prometheus_config.whitelisted_alerts = []
    return collector


def make_namespace(status: str = "unknown"):
    namespace = MagicMock()
    namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: status,
        NamespaceAnnotations.STATUS_TS.value: "2024-01-01T00:00:00Z",
    }
    namespace.metadata.creation_timestamp = datetime.now(timezone.utc)
    return namespace


def test_set_status_updates_annotations_for_ok():
    collector = make_collector()
    namespace = make_namespace()
    collector.patch_namespace = MagicMock()

    collector.set_status(namespace, NamespaceStatus.OK, {})

    collector.patch_namespace.assert_called_once()
    annotations = collector.patch_namespace.call_args.kwargs["annotations"]
    assert annotations[NamespaceAnnotations.STATUS.value] == "ok"
    assert NamespaceAnnotations.STATUS_FINALIZE_AT.value in annotations
    assert NamespaceAnnotations.STATUS_TIMEFRAME.value in annotations


def test_check_namespace_uses_provided_alerts_without_fetch():
    collector = make_collector()
    namespace = make_namespace()
    collector.get_namespace = MagicMock(return_value=namespace)
    collector.fetch_prometheus_alerts = MagicMock()
    collector.evaluate_namespace_health = MagicMock(
        return_value=(NamespaceStatus.OK, {})
    )
    collector.set_status = MagicMock()

    alerts = [{"labels": {"namespace": "ci-test"}}]
    collector.check_namespace(alerts=alerts)

    collector.fetch_prometheus_alerts.assert_not_called()
    collector.evaluate_namespace_health.assert_called_once_with(
        namespace, alerts
    )
    collector.set_status.assert_called_once_with(
        namespace, NamespaceStatus.OK, {}
    )


def test_process_alerts_filters_missing_alertname_and_preserves_runbook():
    collector = make_collector()
    alerts = [
        {
            "labels": {"alertname": "AlertA", "namespace": "ci-test"},
            "annotations": {"runbook_url": "https://runbook"},
        },
        {
            "labels": {"namespace": "ci-test"},
            "annotations": {},
        },
    ]

    with patch.object(collector, "validate_alert", return_value=True):
        processed = collector.process_alerts(alerts)

    assert processed == [
        {
            "labels": {"alertname": "AlertA", "namespace": "ci-test"},
            "annotations": {"runbook_url": "https://runbook"},
        }
    ]


def test_transition_namespace_status_progresses():
    collector = make_collector()

    with patch.object(collector, "_is_after_period", return_value=True):
        unstable = collector.transition_namespace_status(
            {NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value}
        )
        failing = collector.transition_namespace_status(
            {NamespaceAnnotations.STATUS.value: NamespaceStatus.UNSTABLE.value}
        )
        failed = collector.transition_namespace_status(
            {NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILING.value}
        )

    assert unstable == NamespaceStatus.UNSTABLE
    assert failing == NamespaceStatus.FAILING
    assert failed == NamespaceStatus.FAILED


def test_check_resource_status_returns_failing_deployments():
    collector = make_collector()
    resource = MagicMock()
    resource.metadata.name = "deployment-a"
    resource.status.available_replicas = 1
    resource.status.replicas = 2
    collector.apps_v1 = MagicMock()
    collector.apps_v1.list_namespaced_deployment.return_value.items = [
        resource
    ]

    failing = collector._check_resource_status("ci-test", "deployment")

    assert failing == ["deployment-a"]
