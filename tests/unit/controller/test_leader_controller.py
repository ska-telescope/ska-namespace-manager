from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.controller import Controller
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.controller.leader_lock import LeaderLock


@pytest.fixture
def mock_kubernetes_api():
    with patch(
        "ska_ser_namespace_manager.controller.controller.KubernetesAPI",
        autospec=True,
    ) as mock_api_class, patch(
        "ska_ser_namespace_manager.core.kubernetes_api.config.load_kube_config",  # pylint: disable=line-too-long # noqa: E501
        new_callable=MagicMock(),
    ), patch(
        "ska_ser_namespace_manager.core.kubernetes_api.config.load_incluster_config",  # pylint: disable=line-too-long # noqa: E501
        new_callable=MagicMock(),
    ):
        mock_api_instance = mock_api_class.return_value
        mock_api_instance.v1 = MagicMock()

        yield mock_api_instance


@pytest.fixture
def controller(mock_kubernetes_api):
    mock_config_class = MagicMock()
    mock_config_instance = MagicMock()
    mock_config_class.return_value = mock_config_instance
    mock_config_instance.context.namespace = "default-namespace"

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = (
            mock_config_instance
        )
        controller_instance = Controller(
            config_class=mock_config_class, tasks=[]
        )
        yield controller_instance


@pytest.fixture
def leader_controller(controller):
    mock_config_class = MagicMock()
    controller_instance = LeaderController(
        config_class=mock_config_class,
        tasks=[MagicMock(__name__="test")],
        kubeconfig=None,
    )
    yield controller_instance


def test_leader_controller_init_leader_lock(leader_controller):
    assert leader_controller.leader_lock is not None
    assert isinstance(leader_controller.leader_lock, LeaderLock)


def test_leader_controller_acquire_lease_period(leader_controller):
    mock_lease_period = 15
    leader_controller.config.leader_election.lease_ttl.total_seconds.return_value = (  # pylint: disable=line-too-long # noqa: E501
        mock_lease_period * 2
    )
    assert (
        leader_controller._LeaderController__acquire_lease_period()
        == mock_lease_period
    )


def test_leader_controller_is_leader(leader_controller):
    leader_controller.leader_lock.is_leader = MagicMock(return_value=True)
    assert leader_controller.is_leader() is True

    leader_controller.leader_lock.is_leader.return_value = False
    assert leader_controller.is_leader() is False

    leader_controller.config.leader_election.enabled = False
    assert leader_controller.is_leader() is True
