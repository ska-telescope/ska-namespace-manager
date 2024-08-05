from unittest.mock import MagicMock, patch

import pytest
from kubernetes.client.exceptions import ApiException

from ska_ser_namespace_manager.core.kubernetes_api import KubernetesAPI


@pytest.fixture
def mock_kubernetes_api():
    with patch(
        "ska_ser_namespace_manager.core.kubernetes_api.client.CoreV1Api"
    ) as MockCoreV1Api, patch(
        "ska_ser_namespace_manager.core.kubernetes_api.client.AppsV1Api"
    ) as MockAppsV1Api, patch(
        "ska_ser_namespace_manager.core.kubernetes_api.client.BatchV1Api"
    ) as MockBatchV1Api, patch(
        "ska_ser_namespace_manager.core.kubernetes_api.config.load_kube_config",  # pylint: disable=line-too-long # noqa: E501
        new_callable=MagicMock(),
    ) as MockLoadKubeConfig, patch(
        "ska_ser_namespace_manager.core.kubernetes_api.config.load_incluster_config",  # pylint: disable=line-too-long # noqa: E501
        new_callable=MagicMock(),
    ) as MockLoadInclusterConfig:

        # Create mocks for the API instances
        mock_core_v1_api = MockCoreV1Api.return_value
        mock_apps_v1_api = MockAppsV1Api.return_value
        mock_batch_v1_api = MockBatchV1Api.return_value

        yield {
            "mock_core_v1_api": mock_core_v1_api,
            "mock_apps_v1_api": mock_apps_v1_api,
            "mock_batch_v1_api": mock_batch_v1_api,
            "mock_load_kube_config": MockLoadKubeConfig,
            "mock_load_incluster_config": MockLoadInclusterConfig,
        }


def test_load_incluster_kubeconfig(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_load_kube_config = mocks["mock_load_kube_config"]
    mock_load_incluster = mocks["mock_load_incluster_config"]

    KubernetesAPI()
    mock_load_incluster.assert_called_once()
    mock_load_kube_config.assert_not_called()


def test_load_kubeconfig_with_file(mock_kubernetes_api):
    mocks = mock_kubernetes_api

    mock_load_kube_config = mocks["mock_load_kube_config"]
    mock_load_incluster = mocks["mock_load_incluster_config"]

    KubernetesAPI(kubeconfig="path/to/config")
    mock_load_kube_config.assert_called_once_with(config_file="path/to/config")
    mock_load_incluster.assert_not_called()


def test_load_kubeconfig_with_error(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_load_kube_config = mocks["mock_load_kube_config"]
    mock_load_incluster = mocks["mock_load_incluster_config"]

    mock_load_kube_config.side_effect = Exception("Failed to load kubeconfig")

    with pytest.raises(Exception, match="Failed to load kubeconfig"):
        KubernetesAPI(kubeconfig="path/to/config")

    mock_load_kube_config.assert_called_once_with(config_file="path/to/config")
    mock_load_incluster.assert_not_called()


# Test get_namespaces


def test_get_namespaces_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns = MagicMock()
    mock_ns.metadata.name = "test"
    mock_v1.list_namespace.return_value.items = [mock_ns]

    api = KubernetesAPI()
    namespaces = api.get_namespaces()
    assert namespaces == ["test"]
    mock_v1.list_namespace.assert_called_once()


def test_get_namespaces_empty(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.list_namespace.return_value.items = []

    api = KubernetesAPI()
    namespaces = api.get_namespaces()
    assert namespaces == []
    mock_v1.list_namespace.assert_called_once()


def test_get_namespaces_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.list_namespace.side_effect = Exception(
        "Failed to fetch namespaces"
    )

    api = KubernetesAPI()
    namespaces = api.get_namespaces()
    assert namespaces == []
    mock_v1.list_namespace.assert_called_once()


# Test get_namespace


def test_get_namespace_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns = MagicMock()
    mock_ns.metadata.name = "test"
    mock_v1.read_namespace.return_value = mock_ns

    api = KubernetesAPI()
    namespace = api.get_namespace("test")
    assert namespace.metadata.name == "test"
    mock_v1.read_namespace.assert_called_once_with(name="test")


def test_get_namespace_not_found(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.read_namespace.side_effect = ApiException(status=404)

    api = KubernetesAPI()
    namespace = api.get_namespace("nonexistent")
    assert namespace is None
    mock_v1.read_namespace.assert_called_once_with(name="nonexistent")


def test_get_namespace_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.read_namespace.side_effect = Exception("Failed to fetch namespace")

    api = KubernetesAPI()
    namespace = api.get_namespace("test")
    assert namespace is None
    mock_v1.read_namespace.assert_called_once_with(name="test")


# Test get_namespaces_by


def test_get_namespaces_by_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api

    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns = MagicMock()
    mock_ns.metadata.name = "test"
    mock_ns.metadata.labels = {"env": "prod"}
    mock_ns.metadata.annotations = {"team": "dev"}

    mock_v1.list_namespace.return_value.items = [mock_ns]

    api = KubernetesAPI()
    namespaces = api.get_namespaces_by(labels={"env": "prod"})
    assert len(namespaces) == 1
    assert namespaces[0].metadata.name == "test"
    mock_v1.list_namespace.assert_called_once_with(label_selector="env=prod")


def test_get_namespaces_by_exclude_labels(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns1 = MagicMock()
    mock_ns1.metadata.name = "namespace1"
    mock_ns1.metadata.labels = {"env": "prod"}

    mock_ns2 = MagicMock()
    mock_ns2.metadata.name = "namespace2"
    mock_ns2.metadata.labels = {"env": "dev"}

    mock_v1.list_namespace.return_value.items = [mock_ns2]

    api = KubernetesAPI()
    namespaces = api.get_namespaces_by(exclude_labels={"env": "prod"})

    assert len(namespaces) == 1
    assert namespaces[0].metadata.name == "namespace2"
    mock_v1.list_namespace.assert_called_once_with(label_selector="env!=prod")


def test_get_namespaces_by_exclude_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns1 = MagicMock()
    mock_ns1.metadata.name = "namespace1"
    mock_ns1.metadata.annotations = {"team": "dev"}

    mock_ns2 = MagicMock()
    mock_ns2.metadata.name = "namespace2"
    mock_ns2.metadata.annotations = {"team": "ops"}

    mock_v1.list_namespace.return_value.items = [mock_ns2]

    api = KubernetesAPI()
    namespaces = api.get_namespaces_by(exclude_annotations={"team": "dev"})

    assert len(namespaces) == 1
    assert namespaces[0].metadata.name == "namespace2"
    mock_v1.list_namespace.assert_called_once_with(label_selector="")


def test_get_namespaces_by_exclude_labels_and_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns1 = MagicMock()
    mock_ns1.metadata.name = "namespace1"
    mock_ns1.metadata.labels = {"env": "prod"}
    mock_ns1.metadata.annotations = {"team": "dev"}

    mock_ns2 = MagicMock()
    mock_ns2.metadata.name = "namespace2"
    mock_ns2.metadata.labels = {"env": "dev"}
    mock_ns2.metadata.annotations = {"team": "ops"}

    mock_v1.list_namespace.return_value.items = [mock_ns1, mock_ns2]

    api = KubernetesAPI()
    namespaces = api.get_namespaces_by(
        exclude_labels={"env": "prod"}, exclude_annotations={"team": "dev"}
    )

    assert len(namespaces) == 1
    assert namespaces[0].metadata.name == "namespace2"
    mock_v1.list_namespace.assert_called_once_with(label_selector="env!=prod")


def test_get_namespaces_by_no_labels(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_ns = MagicMock()
    mock_ns.metadata.name = "test"
    mock_v1.list_namespace.return_value.items = [mock_ns]

    api = KubernetesAPI()
    namespaces = api.get_namespaces_by()
    assert len(namespaces) == 1
    assert namespaces[0].metadata.name == "test"
    mock_v1.list_namespace.assert_called_once_with(label_selector="")


def test_get_namespaces_by_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api

    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.list_namespace.side_effect = Exception(
        "Failed to fetch namespaces"
    )

    api = KubernetesAPI()
    namespaces = api.get_namespaces_by()
    assert namespaces == []
    mock_v1.list_namespace.assert_called_once()


# Test get_namespace_pods_by


def test_get_namespace_pods_by_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_pod = MagicMock()
    mock_pod.metadata.name = "pod1"
    mock_pod.metadata.labels = {"env": "prod"}
    mock_pod.metadata.annotations = {"team": "dev"}

    mock_v1.list_namespaced_pod.return_value.items = [mock_pod]

    api = KubernetesAPI()
    pods = api.get_namespace_pods_by(
        namespace="default",
        labels={"env": "prod"},
        annotations={"team": "dev"},
    )
    assert len(pods) == 1
    assert pods[0].metadata.name == "pod1"
    mock_v1.list_namespaced_pod.assert_called_once_with(
        namespace="default", label_selector="env=prod"
    )


def test_get_namespace_pods_by_exclude_labels(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_pod1 = MagicMock()
    mock_pod1.metadata.name = "pod1"
    mock_pod1.metadata.labels = {"env": "prod"}

    mock_pod2 = MagicMock()
    mock_pod2.metadata.name = "pod2"
    mock_pod2.metadata.labels = {"env": "dev"}

    mock_v1.list_namespaced_pod.return_value.items = [mock_pod2]

    api = KubernetesAPI()
    pods = api.get_namespace_pods_by(
        namespace="default", exclude_labels={"env": "prod"}
    )

    assert len(pods) == 1
    assert pods[0].metadata.name == "pod2"
    mock_v1.list_namespaced_pod.assert_called_once_with(
        namespace="default", label_selector="env!=prod"
    )


def test_get_namespace_pods_by_exclude_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_pod1 = MagicMock()
    mock_pod1.metadata.name = "pod1"
    mock_pod1.metadata.annotations = {"team": "dev"}

    mock_pod2 = MagicMock()
    mock_pod2.metadata.name = "pod2"
    mock_pod2.metadata.annotations = {"team": "ops"}

    mock_v1.list_namespaced_pod.return_value.items = [mock_pod2]

    api = KubernetesAPI()
    pods = api.get_namespace_pods_by(
        namespace="default", exclude_annotations={"team": "dev"}
    )

    assert len(pods) == 1
    assert pods[0].metadata.name == "pod2"
    mock_v1.list_namespaced_pod.assert_called_once_with(
        namespace="default", label_selector=""
    )


def test_get_namespace_pods_by_exclude_labels_and_annotations(
    mock_kubernetes_api,
):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_pod1 = MagicMock()
    mock_pod1.metadata.name = "pod1"
    mock_pod1.metadata.labels = {"env": "prod"}
    mock_pod1.metadata.annotations = {"team": "dev"}

    mock_pod2 = MagicMock()
    mock_pod2.metadata.name = "pod2"
    mock_pod2.metadata.labels = {"env": "dev"}
    mock_pod2.metadata.annotations = {"team": "ops"}

    mock_v1.list_namespaced_pod.return_value.items = [mock_pod1, mock_pod2]

    api = KubernetesAPI()
    pods = api.get_namespace_pods_by(
        namespace="default",
        exclude_labels={"env": "prod"},
        exclude_annotations={"team": "dev"},
    )

    assert len(pods) == 1
    assert pods[0].metadata.name == "pod2"
    mock_v1.list_namespaced_pod.assert_called_once_with(
        namespace="default", label_selector="env!=prod"
    )


def test_get_namespace_pods_by_empty(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.list_namespaced_pod.return_value.items = []

    api = KubernetesAPI()
    pods = api.get_namespace_pods_by(
        namespace="default", labels={"env": "prod"}
    )
    assert len(pods) == 0
    mock_v1.list_namespaced_pod.assert_called_once_with(
        namespace="default", label_selector="env=prod"
    )


def test_get_namespace_pods_by_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    mock_v1.list_namespaced_pod.side_effect = Exception("Failed to fetch pods")

    api = KubernetesAPI()

    pods = api.get_namespace_pods("default")
    mock_v1.list_namespaced_pod.assert_called_once_with("default")
    assert len(pods) == 0


# Test patch_namespace


def test_patch_namespace_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    api = KubernetesAPI()
    api.patch_namespace(
        "default", labels={"env": "prod"}, annotations={"team": "dev"}
    )
    body = {
        "metadata": {"labels": {"env": "prod"}, "annotations": {"team": "dev"}}
    }
    mock_v1.patch_namespace.assert_called_once_with(name="default", body=body)


def test_patch_namespace_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.patch_namespace.side_effect = Exception(
        "Failed to patch namespace"
    )

    api = KubernetesAPI()
    api.patch_namespace(
        "default", labels={"env": "prod"}, annotations={"team": "dev"}
    )
    mock_v1.patch_namespace.assert_called_once_with(
        name="default",
        body={
            "metadata": {
                "labels": {"env": "prod"},
                "annotations": {"team": "dev"},
            }
        },
    )


# Test delete_namespace


def test_delete_namespace_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]

    api = KubernetesAPI()
    api.delete_namespace("default")
    mock_v1.delete_namespace.assert_called_once_with(
        name="default", grace_period_seconds=0
    )


def test_delete_namespace_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_v1 = mocks["mock_core_v1_api"]
    mock_v1.delete_namespace.side_effect = Exception(
        "Failed to delete namespace"
    )

    api = KubernetesAPI()
    api.delete_namespace("default")
    mock_v1.delete_namespace.assert_called_once_with(
        name="default", grace_period_seconds=0
    )


# Test get_cronjobs_by


def test_get_cronjobs_by_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api

    mock_batch_v1 = mocks["mock_batch_v1_api"]
    mock_batch_v1.list_namespaced_cron_job.return_value.items = [
        MagicMock(
            metadata=MagicMock(
                name="cronjob1", annotations={"cron-type": "daily"}
            )
        )
    ]

    api = KubernetesAPI()
    cronjobs = api.get_cronjobs_by(
        "default", annotations={"cron-type": "daily"}
    )
    assert len(cronjobs) == 1
    assert cronjobs[0].metadata.annotations["cron-type"] == "daily"
    mock_batch_v1.list_namespaced_cron_job.assert_called_once_with(
        namespace="default"
    )


def test_get_cronjobs_by_exclude_labels(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]

    mock_cronjob1 = MagicMock()
    mock_cronjob1.metadata.name = "cronjob1"
    mock_cronjob1.metadata.labels = {"env": "prod"}

    mock_cronjob2 = MagicMock()
    mock_cronjob2.metadata.name = "cronjob2"
    mock_cronjob2.metadata.labels = {"env": "dev"}

    mock_batch_v1.list_namespaced_cron_job.return_value.items = [mock_cronjob2]

    api = KubernetesAPI()
    cronjobs = api.get_cronjobs_by(
        namespace="default", exclude_labels={"env": "prod"}
    )

    assert len(cronjobs) == 1
    assert cronjobs[0].metadata.name == "cronjob2"
    mock_batch_v1.list_namespaced_cron_job.assert_called_once_with(
        namespace="default"
    )


def test_get_cronjobs_by_exclude_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]

    mock_cronjob1 = MagicMock()
    mock_cronjob1.metadata.name = "cronjob1"
    mock_cronjob1.metadata.annotations = {"cron-type": "daily"}

    mock_cronjob2 = MagicMock()
    mock_cronjob2.metadata.name = "cronjob2"
    mock_cronjob2.metadata.annotations = {"cron-type": "weekly"}

    mock_batch_v1.list_namespaced_cron_job.return_value.items = [mock_cronjob2]

    api = KubernetesAPI()
    cronjobs = api.get_cronjobs_by(
        namespace="default", exclude_annotations={"cron-type": "daily"}
    )

    assert len(cronjobs) == 1
    assert cronjobs[0].metadata.name == "cronjob2"
    mock_batch_v1.list_namespaced_cron_job.assert_called_once_with(
        namespace="default"
    )


def test_get_cronjobs_by_exclude_labels_and_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]

    mock_cronjob1 = MagicMock()
    mock_cronjob1.metadata.name = "cronjob1"
    mock_cronjob1.metadata.labels = {"env": "prod"}
    mock_cronjob1.metadata.annotations = {"cron-type": "daily"}

    mock_cronjob2 = MagicMock()
    mock_cronjob2.metadata.name = "cronjob2"
    mock_cronjob2.metadata.labels = {"env": "dev"}
    mock_cronjob2.metadata.annotations = {"cron-type": "weekly"}

    mock_batch_v1.list_namespaced_cron_job.return_value.items = [
        mock_cronjob1,
        mock_cronjob2,
    ]

    api = KubernetesAPI()
    cronjobs = api.get_cronjobs_by(
        namespace="default",
        exclude_labels={"env": "prod"},
        exclude_annotations={"cron-type": "daily"},
    )

    assert len(cronjobs) == 1
    assert cronjobs[0].metadata.name == "cronjob2"
    mock_batch_v1.list_namespaced_cron_job.assert_called_once_with(
        namespace="default"
    )


def test_get_cronjobs_by_empty(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]
    mock_batch_v1.list_namespaced_cron_job.return_value.items = []

    api = KubernetesAPI()
    cronjobs = api.get_cronjobs_by("default")
    assert len(cronjobs) == 0
    mock_batch_v1.list_namespaced_cron_job.assert_called_once_with(
        namespace="default"
    )


def test_get_cronjobs_by_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]
    mock_batch_v1.list_namespaced_cron_job.side_effect = Exception(
        "Failed to fetch cronjobs"
    )

    api = KubernetesAPI()
    cronjobs = api.get_cronjobs_by("default")
    assert len(cronjobs) == 0
    mock_batch_v1.list_namespaced_cron_job.assert_called_once_with(
        namespace="default"
    )


# Test get_jobs_by


def test_get_jobs_by_success(mock_kubernetes_api):
    mocks = mock_kubernetes_api

    mock_batch_v1 = mocks["mock_batch_v1_api"]
    mock_job = MagicMock()
    mock_job.metadata.name = "job1"
    mock_job.metadata.labels = {"env": "prod"}
    mock_job.metadata.annotations = {"team": "dev"}

    mock_batch_v1.list_namespaced_job.return_value.items = [mock_job]

    api = KubernetesAPI()
    jobs = api.get_jobs_by(
        namespace="default",
        labels={"env": "prod"},
        annotations={"team": "dev"},
    )
    assert len(jobs) == 1
    assert jobs[0].metadata.name == "job1"
    mock_batch_v1.list_namespaced_job.assert_called_once_with(
        namespace="default"
    )


def test_get_jobs_by_exclude_labels(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]

    mock_job1 = MagicMock()
    mock_job1.metadata.name = "job1"
    mock_job1.metadata.labels = {"env": "prod"}

    mock_job2 = MagicMock()
    mock_job2.metadata.name = "job2"
    mock_job2.metadata.labels = {"env": "dev"}

    mock_batch_v1.list_namespaced_job.return_value.items = [mock_job2]

    api = KubernetesAPI()
    jobs = api.get_jobs_by(namespace="default", exclude_labels={"env": "prod"})

    assert len(jobs) == 1
    assert jobs[0].metadata.name == "job2"
    mock_batch_v1.list_namespaced_job.assert_called_once_with(
        namespace="default"
    )


def test_get_jobs_by_exclude_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]

    mock_job1 = MagicMock()
    mock_job1.metadata.name = "job1"
    mock_job1.metadata.annotations = {"team": "dev"}

    mock_job2 = MagicMock()
    mock_job2.metadata.name = "job2"
    mock_job2.metadata.annotations = {"team": "ops"}

    mock_batch_v1.list_namespaced_job.return_value.items = [mock_job2]

    api = KubernetesAPI()
    jobs = api.get_jobs_by(
        namespace="default", exclude_annotations={"team": "dev"}
    )

    assert len(jobs) == 1
    assert jobs[0].metadata.name == "job2"
    mock_batch_v1.list_namespaced_job.assert_called_once_with(
        namespace="default"
    )


def test_get_jobs_by_exclude_labels_and_annotations(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]

    mock_job1 = MagicMock()
    mock_job1.metadata.name = "job1"
    mock_job1.metadata.labels = {"env": "prod"}
    mock_job1.metadata.annotations = {"team": "dev"}

    mock_job2 = MagicMock()
    mock_job2.metadata.name = "job2"
    mock_job2.metadata.labels = {"env": "dev"}
    mock_job2.metadata.annotations = {"team": "ops"}

    mock_batch_v1.list_namespaced_job.return_value.items = [
        mock_job1,
        mock_job2,
    ]

    api = KubernetesAPI()
    jobs = api.get_jobs_by(
        namespace="default",
        exclude_labels={"env": "prod"},
        exclude_annotations={"team": "dev"},
    )

    assert len(jobs) == 1
    assert jobs[0].metadata.name == "job2"
    mock_batch_v1.list_namespaced_job.assert_called_once_with(
        namespace="default"
    )


def test_get_jobs_by_empty(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]
    mock_batch_v1.list_namespaced_job.return_value.items = []

    api = KubernetesAPI()
    jobs = api.get_jobs_by(namespace="default", labels={"env": "prod"})
    assert len(jobs) == 0
    mock_batch_v1.list_namespaced_job.assert_called_once_with(
        namespace="default"
    )


def test_get_jobs_by_failure(mock_kubernetes_api):
    mocks = mock_kubernetes_api
    mock_batch_v1 = mocks["mock_batch_v1_api"]
    mock_batch_v1.list_namespaced_job.side_effect = Exception(
        "Failed to fetch jobs"
    )

    api = KubernetesAPI()
    jobs = api.get_jobs_by(namespace="default")
    assert jobs == []
    mock_batch_v1.list_namespaced_job.assert_called_once_with(
        namespace="default"
    )


# Test to_dto


def test_to_dto_conversion(mock_kubernetes_api):
    mock_namespace = MagicMock()
    mock_namespace.metadata = MagicMock()
    mock_namespace.metadata.name = "test-namespace"
    mock_namespace.metadata.labels = {"env": "prod"}
    mock_namespace.metadata.annotations = {"team": "dev"}

    api = KubernetesAPI()
    dto = api.to_dto(mock_namespace)

    assert dto.name == "test-namespace"
    assert dto.labels == {"env": "prod"}
    assert dto.annotations == {"team": "dev"}


def test_to_dto_none(mock_kubernetes_api):
    api = KubernetesAPI()
    dto = api.to_dto(None)
    assert dto is None
