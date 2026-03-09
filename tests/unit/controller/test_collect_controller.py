from datetime import timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.collect_controller import (
    CollectController,
)
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectControllerConfig,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.namespace import Namespace
from ska_ser_namespace_manager.core.types import NamespaceAnnotations


@pytest.fixture
def mock_leader_controller_init():
    with patch.object(
        LeaderController,
        "__init__",
        lambda self, config_class, tasks, kubeconfig: None,
    ):
        yield


@pytest.fixture
def mock_collect_controller_config():
    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.CollectControllerConfig",  # pylint: disable=line-too-long # noqa: E501
        autospec=True,
    ) as mock_config_class:
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.context = MagicMock()
        mock_config_instance.context.namespace = "default-namespace"
        mock_config_instance.leader_election = MagicMock()
        mock_config_instance.leader_election.enabled = True
        mock_config_instance.leader_election.lock_path = "/mock/lock/path"
        mock_config_instance.leader_election.lease_path = "/mock/lease/path"
        mock_config_instance.leader_election.lease_ttl = timedelta(seconds=30)
        mock_config_instance.namespaces = []
        mock_config_instance.sharding = MagicMock()
        mock_config_instance.sharding.enabled = True
        mock_config_instance.sharding.pod_labels = {
            "app.kubernetes.io/component": "collect-controller"
        }
        mock_config_instance.metrics = MagicMock()
        yield mock_config_instance


@pytest.fixture
def collect_controller(
    mock_leader_controller_init, mock_collect_controller_config
):
    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = (
            mock_collect_controller_config
        )

        collect_controller_instance = CollectController.__new__(
            CollectController
        )

        LeaderController.__init__(
            collect_controller_instance,
            CollectControllerConfig,
            [collect_controller_instance.check_new_namespaces],
            None,
        )

        collect_controller_instance.config = mock_collect_controller_config
        collect_controller_instance.forbidden_namespaces = []
        collect_controller_instance.leader_lock = MagicMock()
        collect_controller_instance.shutdown_event = MagicMock()
        collect_controller_instance.shutdown_event.is_set = MagicMock(
            return_value=False
        )
        yield collect_controller_instance


def test_collect_controller_init(
    mock_leader_controller_init, mock_collect_controller_config
):
    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader, patch.object(
        LeaderController, "__init__", return_value=None
    ) as mock_leader_init:

        mock_config_loader.return_value.load.return_value = (
            mock_collect_controller_config
        )

        collect_controller_instance = CollectController.__new__(
            CollectController
        )
        collect_controller_instance.config = mock_collect_controller_config

        LeaderController.__init__(
            collect_controller_instance,
            CollectControllerConfig,
            [collect_controller_instance.check_new_namespaces],
            None,
        )

        assert isinstance(collect_controller_instance, CollectController)
        assert isinstance(collect_controller_instance, LeaderController)
        assert (
            collect_controller_instance.config
            == mock_collect_controller_config
        )
        mock_leader_init.assert_called_once_with(
            collect_controller_instance,
            CollectControllerConfig,
            [collect_controller_instance.check_new_namespaces],
            None,
        )


def test_owns_namespace_when_sharding_disabled(collect_controller):
    collect_controller.config.sharding.enabled = False

    assert collect_controller.owns_namespace("ci-test") is True


def test_owns_namespace_when_replica_matches(collect_controller):
    collect_controller.config.sharding.enabled = True
    collect_controller.get_replica_id = MagicMock(return_value="collect-a")
    collect_controller.get_active_collect_replicas = MagicMock(
        return_value=["collect-a", "collect-b"]
    )

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.NamespaceShardAssigner.owns_namespace",
        return_value=True,
    ) as mock_owns_namespace:
        assert collect_controller.owns_namespace("ci-test") is True

    mock_owns_namespace.assert_called_once_with(
        "ci-test",
        "collect-a",
        ["collect-a", "collect-b"],
    )


def test_check_new_namespaces(collect_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {}

    collect_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    collect_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={},
        )
    )
    collect_controller.patch_namespace = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ):
        collect_controller.check_new_namespaces()

    collect_controller.patch_namespace.assert_called_once_with(
        "test-namespace",
        annotations={
            NamespaceAnnotations.STATUS: "unknown",
            NamespaceAnnotations.MANAGED: "true",
            NamespaceAnnotations.NAMESPACE: "test-namespace",
        },
    )


def test_get_alerts_by_namespace(collect_controller):
    alerts = [
        {"labels": {"namespace": "ci-a", "alertname": "AlertA"}},
        {"labels": {"namespace": "ci-a", "alertname": "AlertB"}},
        {"labels": {"namespace": "ci-b", "alertname": "AlertC"}},
        {"labels": {"alertname": "AlertMissingNamespace"}},
    ]

    alerts_by_namespace = collect_controller._get_alerts_by_namespace(alerts)

    assert len(alerts_by_namespace["ci-a"]) == 2
    assert len(alerts_by_namespace["ci-b"]) == 1
    assert "AlertMissingNamespace" not in str(alerts_by_namespace)


def test_collect_namespace_health(collect_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "ci-test"
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    collect_controller.owns_namespace = MagicMock(return_value=True)
    collect_controller._fetch_prometheus_alerts_snapshot = MagicMock(
        return_value=[{"labels": {"namespace": "ci-test"}}]
    )

    namespace_collector = MagicMock()
    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.NamespaceCollector",
        return_value=namespace_collector,
    ) as mock_namespace_collector:
        collect_controller.collect_namespace_health()

    mock_namespace_collector.assert_called_once_with("ci-test", ANY)
    namespace_collector.check_namespace.assert_called_once_with(
        alerts=[{"labels": {"namespace": "ci-test"}}]
    )


def test_collect_namespace_ownership(collect_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "ci-test"
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    collect_controller.owns_namespace = MagicMock(return_value=True)

    ownership_collector = MagicMock()
    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.OwnershipCollector",
        return_value=ownership_collector,
    ) as mock_ownership_collector:
        collect_controller.collect_namespace_ownership()

    mock_ownership_collector.assert_called_once_with(
        "ci-test",
        ANY,
    )
    ownership_collector.get_owner_info.assert_called_once_with()


def test_generate_metrics(collect_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {}

    collect_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )

    collect_controller.metrics_manager = MagicMock()
    collect_controller.metrics_manager.delete_stale_metrics = MagicMock()
    collect_controller.metrics_manager.update_namespace_metrics = MagicMock()
    collect_controller.metrics_manager.save_metrics = MagicMock()

    collect_controller.generate_metrics()

    collect_controller.metrics_manager.delete_stale_metrics.assert_called_once_with(  # pylint: disable=line-too-long  # noqa: E501
        [mock_namespace.metadata.name]
    )
    collect_controller.metrics_manager.save_metrics.assert_called_once()
