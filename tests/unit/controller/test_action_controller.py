from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.action_controller import (
    ActionController,
)
from ska_ser_namespace_manager.controller.action_controller_config import (
    ActionControllerConfig,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.namespace import Namespace
from ska_ser_namespace_manager.core.notifier import Notifier
from ska_ser_namespace_manager.core.types import (
    NamespaceAnnotations,
    NamespaceStatus,
)


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
            ],
            None,
        )
        Notifier.__init__(
            action_controller_instance,
            mock_action_controller_config.notifier.token,
        )

        action_controller_instance.forbidden_namespaces = []
        action_controller_instance.config = mock_action_controller_config
        action_controller_instance.leader_lock = MagicMock()
        action_controller_instance.shutdown_event = MagicMock()
        action_controller_instance.shutdown_event.is_set = MagicMock(
            return_value=False
        )
        yield action_controller_instance


def test_action_controller_init(
    mock_notifier_init,
    mock_leader_controller_init,
    mock_action_controller_config,
):
    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader, patch(
        "ska_ser_namespace_manager.core.logging.logging.debug"
    ), patch(
        "ska_ser_namespace_manager.controller.action_controller.yaml.safe_dump"
    ) as mock_yaml_dump, patch(
        "ska_ser_namespace_manager.controller.action_controller.yaml.safe_load"
    ) as mock_yaml_load, patch.object(
        LeaderController, "__init__", return_value=None
    ) as mock_leader_init, patch.object(
        Notifier, "__init__", return_value=None
    ) as mock_notifier_init:

        mock_config_loader.return_value.load.return_value = (
            mock_action_controller_config
        )
        mock_yaml_load.return_value = {}
        mock_yaml_dump.return_value = "config dump"

        action_controller_instance = ActionController.__new__(ActionController)
        action_controller_instance.config = mock_action_controller_config

        LeaderController.__init__(
            action_controller_instance,
            ActionControllerConfig,
            [
                action_controller_instance.delete_stale_namespaces,
                action_controller_instance.delete_failed_namespaces,
            ],
            None,
        )
        Notifier.__init__(
            action_controller_instance,
            action_controller_instance.config.notifier.token,
        )

        action_controller_instance.forbidden_namespaces = []
        action_controller_instance.leader_lock = MagicMock()
        action_controller_instance.shutdown_event = MagicMock()
        action_controller_instance.shutdown_event.is_set = MagicMock(
            return_value=False
        )

        assert isinstance(action_controller_instance, ActionController)
        assert isinstance(action_controller_instance, LeaderController)
        assert isinstance(action_controller_instance, Notifier)
        assert (
            action_controller_instance.config == mock_action_controller_config
        )

        mock_leader_init.assert_called_once_with(
            action_controller_instance,
            ActionControllerConfig,
            [
                action_controller_instance.delete_stale_namespaces,
                action_controller_instance.delete_failed_namespaces,
            ],
            None,
        )
        mock_notifier_init.assert_called_once_with(
            action_controller_instance,
            mock_action_controller_config.notifier.token,
        )


def test_delete_namespaces_with_status_no_match(action_controller):
    action_controller.get_namespaces_by = MagicMock(return_value=[])
    action_controller.delete_namespaces_with_status("stale")
    action_controller.get_namespaces_by.assert_called_once_with(
        annotations={
            NamespaceAnnotations.MANAGED.value: "true",
            NamespaceAnnotations.STATUS.value: NamespaceStatus.STALE.value,
        }
    )


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
        action_controller.delete_namespaces_with_status(
            NamespaceStatus.STALE.value
        )

    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )
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
        action_controller.delete_namespaces_with_status("stale")

    action_controller.delete_namespace.assert_called_once_with(
        "test-namespace"
    )
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
        action_controller.delete_namespaces_with_status("stale")

    action_controller.delete_namespace.assert_not_called()
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
        action_controller.delete_namespaces_with_status(
            NamespaceStatus.STALE.value
        )

    action_controller.delete_namespace.assert_not_called()
    action_controller.notify_user.assert_not_called()


def test_delete_stale_namespaces(action_controller):
    action_controller.delete_namespaces_with_status = MagicMock()
    action_controller.delete_stale_namespaces()
    action_controller.delete_namespaces_with_status.assert_called_once_with(
        NamespaceStatus.STALE.value
    )


def test_delete_failed_namespaces(action_controller):
    action_controller.delete_namespaces_with_status = MagicMock()
    action_controller.delete_failed_namespaces()
    action_controller.delete_namespaces_with_status.assert_called_once_with(
        NamespaceStatus.FAILED.value
    )


def test_notify_failing_unstable_namespaces_no_match(action_controller):
    action_controller.get_namespaces_by = MagicMock(return_value=[])
    action_controller.notify_failing_unstable_namespaces()
    action_controller.get_namespaces_by.assert_called_once_with(
        annotations={
            NamespaceAnnotations.MANAGED.value: "true",
            NamespaceAnnotations.STATUS.value: "(failing|unstable)",
            NamespaceAnnotations.OWNER.value: ".+",
        },
        exclude_annotations={NamespaceAnnotations.NOTIFIED_TS.value: ".+"},
    )


def test_notify_failing_unstable_namespaces_match(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILING.value,
        NamespaceAnnotations.OWNER.value: "test-owner",
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
                NamespaceAnnotations.OWNER.value: "test-owner",
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
        action_controller.notify_failing_unstable_namespaces()

    action_controller.notify_user.assert_called_once()
    action_controller.patch_namespace.assert_called_once()


def test_notify_failing_unstable_namespaces_match_no_notify(action_controller):
    mock_namespace = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: "failing",
        NamespaceAnnotations.OWNER.value: "test-owner",
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
                NamespaceAnnotations.OWNER.value: "test-owner",
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
        action_controller.notify_failing_unstable_namespaces()

    action_controller.notify_user.assert_not_called()
    action_controller.patch_namespace.assert_not_called()
