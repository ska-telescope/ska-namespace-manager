from datetime import timedelta
from unittest.mock import ANY, MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.collect_controller import (
    CollectController,
)
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
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
        collect_controller_instance.namespace_cronjobs = [
            CollectActions.CHECK_NAMESPACE
        ]
        collect_controller_instance.namespace_jobs = [
            CollectActions.GET_OWNER_INFO
        ]
        yield collect_controller_instance


def test_collect_controller_init(
    mock_leader_controller_init, mock_collect_controller_config
):
    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader, patch(
        "ska_ser_namespace_manager.controller.collect_controller.yaml.safe_dump"  # pylint: disable=line-too-long # noqa: E501
    ) as mock_yaml_dump, patch(
        "ska_ser_namespace_manager.controller.collect_controller.yaml.safe_load"  # pylint: disable=line-too-long # noqa: E501
    ) as mock_yaml_load, patch.object(
        LeaderController, "__init__", return_value=None
    ) as mock_leader_init:

        mock_config_loader.return_value.load.return_value = (
            mock_collect_controller_config
        )
        mock_yaml_load.return_value = {}
        mock_yaml_dump.return_value = "config dump"

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

        collect_controller_instance.namespace_cronjobs = [
            CollectActions.CHECK_NAMESPACE
        ]
        collect_controller_instance.namespace_jobs = [
            CollectActions.GET_OWNER_INFO
        ]

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
    collect_controller.create_collect_cronjob = MagicMock()
    collect_controller.create_collect_job = MagicMock()
    collect_controller.patch_namespace = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=True,
    ):
        collect_controller.check_new_namespaces()

    collect_controller.create_collect_cronjob.assert_called_once_with(
        CollectActions.CHECK_NAMESPACE, "test-namespace", True
    )
    collect_controller.create_collect_job.assert_called_once_with(
        CollectActions.GET_OWNER_INFO, "test-namespace", True
    )
    collect_controller.patch_namespace.assert_called_once_with(
        "test-namespace",
        annotations={
            NamespaceAnnotations.STATUS: "unknown",
            NamespaceAnnotations.MANAGED: "true",
            NamespaceAnnotations.NAMESPACE: "test-namespace",
        },
    )


def test_create_collect_cronjob(collect_controller):
    collect_controller.template_factory = MagicMock()
    collect_controller.template_factory.render = MagicMock(
        return_value="manifest"
    )
    collect_controller.get_cronjobs_by = MagicMock(return_value=[])
    collect_controller.batch_v1 = MagicMock()

    collect_controller.config.prometheus = MagicMock()

    with patch.object(collect_controller.config.prometheus, "enabled", False):
        collect_controller.create_collect_cronjob(
            CollectActions.CHECK_NAMESPACE, "test-namespace", MagicMock()
        )

    collect_controller.template_factory.render.assert_called_once()
    collect_controller.batch_v1.create_namespaced_cron_job.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        collect_controller.config.context.namespace,
        "manifest",
        _request_timeout=10,
    )


def test_create_collect_cronjob_existing(collect_controller):
    mock_cronjob = MagicMock()
    mock_cronjob.metadata.name = "test"
    collect_controller.template_factory = MagicMock()
    collect_controller.template_factory.render = MagicMock(
        return_value="manifest"
    )
    collect_controller.get_cronjobs_by = MagicMock(return_value=[mock_cronjob])
    collect_controller.batch_v1 = MagicMock()

    collect_controller.create_collect_cronjob(
        CollectActions.CHECK_NAMESPACE, "test-namespace", MagicMock()
    )

    collect_controller.template_factory.render.assert_called_once()
    collect_controller.batch_v1.patch_namespaced_cron_job.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        "test",
        collect_controller.config.context.namespace,
        "manifest",
        _request_timeout=10,
    )


def test_synchronize_cronjobs(collect_controller):
    collect_controller.get_cronjobs_by = MagicMock(return_value=[])
    collect_controller.batch_v1 = MagicMock()

    collect_controller.synchronize_cronjobs()

    collect_controller.get_cronjobs_by.assert_called_once()
    collect_controller.batch_v1.patch_namespaced_cron_job.assert_not_called()


def test_synchronize_cronjobs_no_namespace(collect_controller):
    mock_cronjob = MagicMock()
    mock_cronjob.metadata.annotations.get.return_value = True
    collect_controller.get_cronjobs_by = MagicMock(return_value=None)
    collect_controller.batch_v1 = MagicMock()
    collect_controller.get_namespace = MagicMock(return_value=None)

    collect_controller.synchronize_cronjobs()

    collect_controller.get_cronjobs_by.assert_called_once()
    collect_controller.get_namespace.assert_not_called()


def test_synchronize_jobs(collect_controller):
    collect_controller.get_jobs_by = MagicMock(return_value=[])
    collect_controller.batch_v1 = MagicMock()

    collect_controller.synchronize_jobs()

    collect_controller.get_jobs_by.assert_called_once()
    collect_controller.batch_v1.patch_namespaced_job.assert_not_called()


def test_synchronize_jobs_delete_jobs(collect_controller):
    mock_job = MagicMock()
    mock_job.metadata.name = "test-job"
    mock_job.metadata.annotations.get.return_value = "test-namespace"
    collect_controller.get_jobs_by = MagicMock(return_value=[mock_job])
    collect_controller.get_namespace = MagicMock(return_value=None)
    collect_controller.batch_v1 = MagicMock()
    mock_pod = MagicMock()
    mock_pod.metadata.name = "test"
    collect_controller.get_namespace_pods_by = MagicMock(
        return_value=[mock_pod, mock_pod]
    )
    collect_controller.v1 = MagicMock()

    collect_controller.synchronize_jobs()

    collect_controller.get_jobs_by.assert_called_once()
    collect_controller.batch_v1.delete_namespaced_job.assert_called_once_with(
        "test-job",
        "default-namespace",
        propagation_policy="Background",
        _request_timeout=10,
    )


def test_create_collect_job(collect_controller):
    collect_controller.template_factory = MagicMock()
    collect_controller.template_factory.render = MagicMock(
        return_value='{"metadata": {"annotations": {}}}'
    )
    collect_controller.get_jobs_by = MagicMock(return_value=[])
    collect_controller.batch_v1 = MagicMock()

    collect_controller.create_collect_job(
        CollectActions.GET_OWNER_INFO, "test-namespace", MagicMock()
    )

    collect_controller.template_factory.render.assert_called_once()
    collect_controller.batch_v1.create_namespaced_job.assert_called_once_with(
        collect_controller.config.context.namespace,
        {"metadata": {"annotations": ANY}},
        _request_timeout=10,
    )


def test_create_collect_job_existing(collect_controller):
    mock_job = MagicMock()
    mock_job.metadata.name = "test"
    collect_controller.template_factory = MagicMock()
    collect_controller.template_factory.render = MagicMock(
        return_value='{"metadata": {"annotations": {}}}'
    )
    collect_controller.get_jobs_by = MagicMock(return_value=[mock_job])
    collect_controller.batch_v1 = MagicMock()
    collect_controller.wait_for_job_deletion = MagicMock()

    collect_controller.create_collect_job(
        CollectActions.CHECK_NAMESPACE, "test-namespace", MagicMock()
    )

    collect_controller.template_factory.render.assert_called_once()
    collect_controller.batch_v1.delete_namespaced_job.assert_called_once_with(
        "test",
        collect_controller.config.context.namespace,
        propagation_policy="Background",
        _request_timeout=10,
    )


def test_delete_cronjob_for_missing_namespace(collect_controller):
    mock_cronjob = MagicMock()
    mock_cronjob.metadata.annotations = {
        NamespaceAnnotations.NAMESPACE: "missing-namespace"
    }

    collect_controller.get_cronjobs_by = MagicMock(return_value=[mock_cronjob])
    collect_controller.get_namespace = MagicMock(return_value=None)
    collect_controller.batch_v1 = MagicMock()

    collect_controller.synchronize_cronjobs()

    collect_controller.batch_v1.delete_namespaced_cron_job.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        mock_cronjob.metadata.name,
        collect_controller.config.context.namespace,
        _request_timeout=10,
    )


def test_delete_job_for_missing_namespace(collect_controller):
    mock_job = MagicMock()
    mock_job.metadata.annotations = {
        NamespaceAnnotations.NAMESPACE: "missing-namespace"
    }

    collect_controller.get_jobs_by = MagicMock(return_value=[mock_job])
    collect_controller.get_namespace = MagicMock(return_value=None)
    collect_controller.batch_v1 = MagicMock()
    collect_controller.v1 = MagicMock()

    collect_controller.synchronize_jobs()

    collect_controller.batch_v1.delete_namespaced_job.assert_called_once_with(
        mock_job.metadata.name,
        collect_controller.config.context.namespace,
        propagation_policy="Background",
        _request_timeout=10,
    )


def test_patch_cronjob_for_existing_namespace(collect_controller):
    mock_cronjob = MagicMock()
    mock_cronjob.metadata.annotations = {
        NamespaceAnnotations.NAMESPACE: "test-namespace"
    }

    mock_namespace = MagicMock()
    collect_controller.get_cronjobs_by = MagicMock(return_value=[mock_cronjob])
    collect_controller.get_namespace = MagicMock(return_value=mock_namespace)
    collect_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={},
        )
    )
    collect_controller.template_factory = MagicMock()
    collect_controller.template_factory.render = MagicMock(
        return_value="manifest"
    )
    collect_controller.batch_v1 = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=MagicMock(),
    ):
        collect_controller.synchronize_cronjobs()

    collect_controller.batch_v1.patch_namespaced_cron_job.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        mock_cronjob.metadata.name,
        collect_controller.config.context.namespace,
        "manifest",
        _request_timeout=10,
    )


def test_delete_job_for_existing_namespace(collect_controller):
    mock_job = MagicMock()
    mock_job.metadata.annotations = {
        NamespaceAnnotations.NAMESPACE: "test-namespace"
    }

    mock_namespace = MagicMock()
    collect_controller.get_jobs_by = MagicMock(return_value=[mock_job])
    collect_controller.get_namespace = MagicMock(return_value=mock_namespace)
    collect_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={},
        )
    )
    collect_controller.template_factory = MagicMock()
    collect_controller.template_factory.render = MagicMock(
        return_value="manifest"
    )
    collect_controller.batch_v1 = MagicMock()

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=MagicMock(),
    ):
        collect_controller.synchronize_jobs()

    collect_controller.batch_v1.delete_namespaced_job.assert_called_once_with(
        mock_job.metadata.name,
        collect_controller.config.context.namespace,
        propagation_policy="Background",
        _request_timeout=10,
    )


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
