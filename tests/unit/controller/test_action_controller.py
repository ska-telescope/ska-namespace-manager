import json
import logging
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.action_controller import (
    ActionController,
)
from ska_ser_namespace_manager.controller.action_controller_config import (
    ActionControllerConfig,
    ActionNamespaceConfig,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.namespace import Namespace
from ska_ser_namespace_manager.core.notifier import Notifier
from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


@pytest.fixture
def mock_kubernetes_api():
    with patch(
        "ska_ser_namespace_manager.controller.controller.KubernetesAPI",
        autospec=True,
    ) as mock_api_class:
        mock_api_instance = mock_api_class.return_value
        mock_api_instance.v1 = MagicMock()
        yield mock_api_instance


@pytest.fixture
def mock_notifier_init():
    with patch.object(Notifier, "__init__", lambda self, token: None):
        yield


@pytest.fixture
def mock_leader_controller_init():
    with patch.object(
        LeaderController,
        "__init__",
        lambda self, config_class, tasks, kubeconfig: None,
    ):
        yield


@pytest.fixture
def mock_action_controller_config():
    with patch(
        "ska_ser_namespace_manager.controller.action_controller.ActionControllerConfig",  # pylint: disable=line-too-long # noqa: E501
        autospec=True,
    ) as mock_config_class:
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.notifier = MagicMock()
        mock_config_instance.notifier.token = "test-token"
        mock_config_instance.context = MagicMock()
        mock_config_instance.context.namespace = "default-namespace"
        mock_config_instance.leader_election = MagicMock()
        mock_config_instance.leader_election.enabled = True
        mock_config_instance.leader_election.lock_path = "/mock/lock/path"
        mock_config_instance.leader_election.lease_path = "/mock/lease/path"
        mock_config_instance.leader_election.lease_ttl = timedelta(seconds=30)
        mock_config_instance.namespaces = []
        mock_config_instance.metrics = MagicMock()
        mock_config_instance.metrics.enabled = True
        yield mock_config_instance


@pytest.fixture
def action_controller(
    mock_kubernetes_api,
    mock_notifier_init,
    mock_leader_controller_init,
    mock_action_controller_config,
):
    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = (
            mock_action_controller_config
        )

        action_controller_instance = ActionController.__new__(ActionController)

        LeaderController.__init__(
            action_controller_instance,
            ActionControllerConfig,
            [
                action_controller_instance.delete_stale_namespaces,
                action_controller_instance.delete_failed_namespaces,
                action_controller_instance.delete_cancelled_namespaces,
                action_controller_instance.delete_superseded_namespaces,
                action_controller_instance.notify_status_namespaces,
            ],
            None,
        )
        Notifier.__init__(
            action_controller_instance,
            mock_action_controller_config.notifier.token,
        )

        action_controller_instance.forbidden_namespaces = []
        action_controller_instance.config = mock_action_controller_config
        action_controller_instance.metrics_manager = MagicMock()
        action_controller_instance.leader_lock = MagicMock()
        action_controller_instance.shutdown_event = MagicMock()
        action_controller_instance.shutdown_event.is_set = MagicMock(
            return_value=False
        )
        yield action_controller_instance


def test_action_controller_init():
    action_controller_config = MagicMock()
    action_controller_config.notifier.token = "test-token"
    action_controller_config.metrics = MagicMock()

    def mock_environ_get(key, default=None):
        return "action-controller-0" if key == "HOSTNAME" else default

    def set_controller_config(controller, config_class, tasks, kubeconfig):
        controller.config = action_controller_config
        controller.tasks = tasks
        controller.kubeconfig = kubeconfig
        controller.config_class = config_class

    with patch.object(
        LeaderController, "__init__", autospec=True
    ) as mock_leader_init, patch.object(
        Notifier, "__init__", autospec=True, return_value=None
    ) as notifier_init, patch(
        "ska_ser_namespace_manager.controller.action_controller."
        "os.environ.get",
        side_effect=mock_environ_get,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller."
        "MetricsManager",
        autospec=True,
    ) as metrics_manager:
        mock_leader_init.side_effect = set_controller_config
        action_controller_instance = ActionController()

        assert isinstance(action_controller_instance, ActionController)
        assert isinstance(action_controller_instance, LeaderController)
        assert isinstance(action_controller_instance, Notifier)
        assert action_controller_instance.config == action_controller_config

        mock_leader_init.assert_called_once()
        controller, config_class, tasks, kubeconfig = (
            mock_leader_init.call_args.args
        )
        assert controller == action_controller_instance
        assert config_class == ActionControllerConfig
        assert [task.__name__ for task in tasks] == [
            "delete_stale_namespaces",
            "delete_failed_namespaces",
            "delete_cancelled_namespaces",
            "delete_superseded_namespaces",
            "notify_status_namespaces",
        ]
        assert kubeconfig is None
        assert action_controller_instance.current_pod_name == (
            "action-controller-0"
        )
        metrics_manager.assert_called_once_with(
            action_controller_config.metrics,
            owner="action-controller-0",
        )
        notifier_init.assert_called_once_with(
            action_controller_instance,
            action_controller_config.notifier.token,
        )


def test_action_controller_config_has_metrics_default():
    """
    Action controller config should include metrics configuration.
    """
    config = ActionControllerConfig(
        namespaces=[],
        context={
            "namespace": "default-namespace",
            "service_account": "action-ctl-sa",
            "image": "test-image",
            "config_path": "/etc/config",
            "config_secret": "action-config",
        },
        leader_election={},
    )

    assert isinstance(config.metrics, MetricsConfig)


def test_delete_namespaces_with_status_no_match(action_controller):
    action_controller.get_namespaces_by = MagicMock(return_value=[])
    action_controller._delete_namespaces_with_status("stale")
    action_controller.get_namespaces_by.assert_called_once_with(
        annotations={
            NamespaceAnnotations.MANAGED.value: "true",
            NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value,
        }
    )
    action_controller.metrics_manager.record_namespace_deletion.assert_not_called()  # pylint: disable=line-too-long # noqa: E501
    action_controller.metrics_manager.save_metrics.assert_not_called()


def test_delete_namespaces_with_status_match(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value
    }
    mock_namespace.status.phase = "Active"

    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value
            },
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = True
    phase_config.notify_on_delete = True

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller._delete_namespaces_with_status(
            NamespaceStatus.STALE.value
        )

    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )
    action_controller.metrics_manager.record_namespace_deletion.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        NamespaceStatus.STALE.value
    )
    action_controller.metrics_manager.save_metrics.assert_called_once_with()
    action_controller.notify_user.assert_called_once()


def test_delete_namespaces_with_status_match_no_notify(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: "stale"
    }
    mock_namespace.status.phase = "Active"

    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={NamespaceAnnotations.STATUS.value: "stale"},
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = True
    phase_config.notify_on_delete = False

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller._delete_namespaces_with_status("stale")

    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )
    action_controller.metrics_manager.record_namespace_deletion.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        NamespaceStatus.STALE.value
    )
    action_controller.metrics_manager.save_metrics.assert_called_once_with()
    action_controller.notify_user.assert_not_called()


def test_delete_namespaces_with_status_match_metrics_disabled(
    action_controller,
):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: "stale"
    }
    mock_namespace.status.phase = "Active"

    action_controller.config.metrics.enabled = False
    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={NamespaceAnnotations.STATUS.value: "stale"},
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = True
    phase_config.notify_on_delete = False

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller._delete_namespaces_with_status("stale")

    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )
    action_controller.metrics_manager.record_namespace_deletion.assert_not_called()  # pylint: disable=line-too-long # noqa: E501
    action_controller.metrics_manager.save_metrics.assert_not_called()
    action_controller.notify_user.assert_not_called()


def test_delete_namespaces_with_status_match_no_delete(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: "stale"
    }
    mock_namespace.status.phase = "Active"

    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={NamespaceAnnotations.STATUS.value: "stale"},
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = False
    phase_config.notify_on_delete = False

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller._delete_namespaces_with_status("stale")

    action_controller.delete_namespace.assert_not_called()
    action_controller.metrics_manager.record_namespace_deletion.assert_not_called()  # pylint: disable=line-too-long # noqa: E501
    action_controller.metrics_manager.save_metrics.assert_not_called()
    action_controller.notify_user.assert_not_called()


def test_delete_namespaces_with_status_terminating(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value
    }
    mock_namespace.status.phase = "Terminating"

    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value
            },
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = True
    phase_config.notify_on_delete = True

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller._delete_namespaces_with_status(
            NamespaceStatus.STALE.value
        )

    action_controller.delete_namespace.assert_not_called()
    action_controller.metrics_manager.record_namespace_deletion.assert_not_called()  # pylint: disable=line-too-long # noqa: E501
    action_controller.metrics_manager.save_metrics.assert_not_called()
    action_controller.notify_user.assert_not_called()


def test_delete_stale_namespaces(action_controller):
    action_controller._delete_namespaces_with_status = MagicMock()
    action_controller.delete_stale_namespaces()
    action_controller._delete_namespaces_with_status.assert_called_once_with(
        NamespaceStatus.STALE.value
    )


def test_delete_failed_namespaces(action_controller):
    action_controller._delete_namespaces_with_status = MagicMock()
    action_controller.delete_failed_namespaces()
    action_controller._delete_namespaces_with_status.assert_called_once_with(
        NamespaceStatus.FAILED.value
    )


def test_delete_cancelled_namespaces(action_controller):
    action_controller._delete_namespaces_with_status = MagicMock()
    action_controller.delete_cancelled_namespaces()
    action_controller._delete_namespaces_with_status.assert_called_once_with(
        NamespaceStatus.CANCELLED.value
    )


def test_delete_superseded_namespaces(action_controller):
    action_controller._delete_namespaces_with_status = MagicMock()
    action_controller.delete_superseded_namespaces()
    action_controller._delete_namespaces_with_status.assert_called_once_with(
        NamespaceStatus.SUPERSEDED.value
    )


def test_action_namespace_config_terminal_defaults():
    """Cancelled and superseded action configs should notify and delete."""
    config = ActionNamespaceConfig(names=["ci-.*"])

    assert config.cancelled.delete is True
    assert config.cancelled.notify_on_delete is False
    assert config.cancelled.notify_on_status is True
    assert config.superseded.delete is True
    assert config.superseded.notify_on_delete is False
    assert config.superseded.notify_on_status is True


def test_notify_status_namespaces_no_match(action_controller):
    action_controller.get_namespaces_by = MagicMock(return_value=[])
    action_controller.notify_status_namespaces()
    action_controller.get_namespaces_by.assert_called_once_with(
        annotations={
            NamespaceAnnotations.MANAGED.value: "true",
            NamespaceAnnotations.STATUS.value: (
                "(failing|unstable|cancelled|superseded)"
            ),
            CicdAnnotations.NOTIFICATION_ADDRESS.value: ".+",
        },
        exclude_annotations={NamespaceAnnotations.NOTIFIED_TS.value: ".+"},
    )


def test_notify_status_namespaces_match(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILING.value,
        CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
    }
    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILING.value,  # pylint: disable=line-too-long # noqa: E501
                CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
            },
        )
    )
    phase_config = MagicMock()
    phase_config.delete = False
    phase_config.notify_on_delete = False
    phase_config.notify_on_status = True
    action_controller.notify_user = MagicMock(return_value=True)
    action_controller.patch_namespace = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller.notify_status_namespaces()

    action_controller.notify_user.assert_called_once()
    action_controller.patch_namespace.assert_called_once()


def test_notify_status_namespaces_cancelled(action_controller):
    """Cancelled status should use the cancelled notification template."""
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.CANCELLED.value,
        CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
    }
    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.CANCELLED.value,  # pylint: disable=line-too-long # noqa: E501
                CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
            },
        )
    )
    phase_config = MagicMock()
    phase_config.notify_on_status = True
    action_controller.notify_user = MagicMock(return_value=True)
    action_controller.patch_namespace = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller.notify_status_namespaces()

    action_controller.notify_user.assert_called_once()
    assert (
        action_controller.notify_user.call_args.kwargs["template"]
        == "cancelled-namespace-notification.j2"
    )
    action_controller.patch_namespace.assert_called_once()


def test_notify_status_namespaces_superseded(action_controller):
    """Superseded status should use the superseded notification template."""
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.SUPERSEDED.value,
        CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
    }
    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={
                NamespaceAnnotations.STATUS.value: (
                    NamespaceStatus.SUPERSEDED.value
                ),
                CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
            },
        )
    )
    phase_config = MagicMock()
    phase_config.notify_on_status = True
    action_controller.notify_user = MagicMock(return_value=True)
    action_controller.patch_namespace = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.action_controller."
        "match_namespace",
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller.notify_status_namespaces()

    action_controller.notify_user.assert_called_once()
    assert (
        action_controller.notify_user.call_args.kwargs["template"]
        == "superseded-namespace-notification.j2"
    )
    action_controller.patch_namespace.assert_called_once()


def test_notify_status_namespaces_match_no_notify(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: "failing",
        CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
    }
    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={
                NamespaceAnnotations.STATUS.value: "failing",
                CicdAnnotations.NOTIFICATION_ADDRESS.value: "test-address",
            },
        )
    )
    phase_config = MagicMock()
    phase_config.delete = False
    phase_config.notify_on_delete = False
    phase_config.notify_on_status = False

    action_controller.notify_user = MagicMock(return_value=True)
    action_controller.patch_namespace = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ):
        action_controller.notify_status_namespaces()

    action_controller.notify_user.assert_not_called()
    action_controller.patch_namespace.assert_not_called()


def test_summarize_failing_resources_empty(action_controller):
    assert action_controller._summarize_failing_resources("") == ""
    assert action_controller._summarize_failing_resources("[]") == ""


def test_summarize_failing_resources_invalid_json(action_controller):
    assert (
        action_controller._summarize_failing_resources("not-json")
        == "not-json"
    )


def test_summarize_failing_resources_string_list(action_controller):
    resources_json = json.dumps(["my-deployment", "my-statefulset"])
    assert (
        action_controller._summarize_failing_resources(resources_json)
        == "my-deployment, my-statefulset"
    )


def test_summarize_failing_resources_alert_dicts(action_controller):
    resources_json = json.dumps(
        [
            {
                "labels": {
                    "alertname": "KubePodNotReady",
                    "pod": "my-pod",
                },
                "annotations": {},
            },
            {
                "labels": {"alertname": "SomeAlert"},
                "annotations": {},
            },
        ]
    )
    assert action_controller._summarize_failing_resources(resources_json) == (
        "KubePodNotReady: pod=my-pod; SomeAlert"
    )


def test_delete_namespaces_logs_failing_resources(action_controller, caplog):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILED.value,
        NamespaceAnnotations.FAILING_RESOURCES.value: json.dumps(
            ["my-deployment"]
        ),
    }
    mock_namespace.status.phase = "Active"

    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace", labels={}, annotations={}
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = True
    phase_config.notify_on_delete = False

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ), caplog.at_level(logging.INFO):
        action_controller._delete_namespaces_with_status(
            NamespaceStatus.FAILED.value
        )

    assert (
        "had failing resources before deletion: my-deployment" in caplog.text
    )
    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )


def test_delete_namespaces_no_failing_resources_no_log(
    action_controller, caplog
):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value
    }
    mock_namespace.status.phase = "Active"

    action_controller.get_namespaces_by = MagicMock(
        return_value=[mock_namespace]
    )
    action_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace", labels={}, annotations={}
        )
    )
    action_controller.delete_namespace = MagicMock()
    action_controller.notify_user = MagicMock()

    phase_config = MagicMock()
    phase_config.delete = True
    phase_config.notify_on_delete = False

    with patch(
        "ska_ser_namespace_manager.controller.action_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.getattr",
        return_value=phase_config,
    ), caplog.at_level(logging.INFO):
        action_controller._delete_namespaces_with_status(
            NamespaceStatus.STALE.value
        )

    assert "had failing resources before deletion" not in caplog.text
    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )
