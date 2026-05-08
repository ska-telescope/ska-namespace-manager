"""
Tests for collect controller orchestration and sharding behavior.
"""

import hashlib
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.collect_controller import (
    CollectController,
)
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CheckOptions,
    CollectActions,
    CollectControllerConfig,
    CollectNamespaceConfig,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.namespace import Namespace
from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)


def _make_pod(
    name: str,
    service_account_name: str,
    deleting=False,
    labels=None,
):
    """Build a pod-like mock for replica discovery tests."""
    pod = MagicMock()
    pod.metadata = MagicMock()
    pod.metadata.name = name
    pod.metadata.labels = labels or {}
    pod.metadata.deletion_timestamp = (
        datetime.now(timezone.utc) if deleting else None
    )
    pod.spec = MagicMock()
    pod.spec.service_account_name = service_account_name
    return pod


def _make_namespace(
    name: str,
    created: datetime,
    labels: dict | None = None,
    annotations: dict | None = None,
    phase: str = "Active",
):
    """Build a namespace-like object for controller tests."""
    return SimpleNamespace(
        metadata=SimpleNamespace(
            name=name,
            creation_timestamp=created,
            labels=labels or {},
            annotations=annotations
            or {NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value},
        ),
        status=SimpleNamespace(phase=phase),
    )


def _ci_labels(project_id="123", branch="main", mr_id=None):
    """Build CI labels used for superseded detection."""
    labels = {
        CicdAnnotations.PROJECT_ID.value: project_id,
    }
    if branch is not None:
        labels[CicdAnnotations.BRANCH.value] = branch
    if mr_id is not None:
        labels[CicdAnnotations.MR_ID.value] = mr_id

    return labels


@pytest.fixture(name="mock_leader_controller_init", autouse=True)
def mock_leader_controller_init_fixture():
    """Patch the leader controller init for isolated controller tests."""
    with patch.object(
        LeaderController,
        "__init__",
        lambda self, config_class, tasks, kubeconfig: None,
    ):
        yield


@pytest.fixture(name="mock_collect_controller_config")
def mock_collect_controller_config_fixture():
    """Build a collect-controller config fixture for unit tests."""
    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.CollectControllerConfig",  # pylint: disable=line-too-long # noqa: E501
        autospec=True,
    ) as mock_config_class:
        mock_config_instance = mock_config_class.return_value
        mock_config_instance.context = MagicMock()
        mock_config_instance.context.namespace = "default-namespace"
        mock_config_instance.context.service_account = "collect-ctl-sa"
        mock_config_instance.leader_election = MagicMock()
        mock_config_instance.leader_election.enabled = True
        mock_config_instance.leader_election.lock_path = "/mock/lock/path"
        mock_config_instance.leader_election.lease_path = "/mock/lease/path"
        mock_config_instance.leader_election.lease_ttl = timedelta(seconds=30)
        mock_config_instance.heartbeat = MagicMock()
        mock_config_instance.namespaces = []
        mock_config_instance.metrics = MagicMock()
        yield mock_config_instance


@pytest.fixture(name="collect_controller")
def collect_controller_fixture(mock_collect_controller_config, tmp_path):
    """Build a partially initialized collect controller for unit tests."""
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
            [
                collect_controller_instance.check_new_namespaces,
                collect_controller_instance.check_superseded_namespaces,
            ],
            None,
        )

        collect_controller_instance.config = mock_collect_controller_config
        collect_controller_instance.config.heartbeat.path = str(
            tmp_path / "collect-controller-heartbeat"
        )
        collect_controller_instance.config.heartbeat.max_age_seconds = 60
        collect_controller_instance.forbidden_namespaces = []
        collect_controller_instance.leader_lock = MagicMock()
        collect_controller_instance.shutdown_event = MagicMock()
        collect_controller_instance.shutdown_event.is_set = MagicMock(
            return_value=False
        )
        collect_controller_instance.current_pod_name = "collect-1"
        collect_controller_instance.namespace_check_threads = {}
        collect_controller_instance.namespace_collector = MagicMock()
        collect_controller_instance.kubeconfig = None
        collect_controller_instance.threads = {}
        collect_controller_instance.task_stop_events = {}
        collect_controller_instance.is_running = False
        yield collect_controller_instance


def test_check_new_namespaces(collect_controller):
    """New namespaces should create owner jobs and become managed."""
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


def test_check_superseded_namespaces_groups_by_mr(collect_controller):
    """Namespaces with the same project and MR should supersede by age."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old_namespace = _make_namespace(
        "ci-old",
        base_time,
        labels=_ci_labels(branch="feature-a", mr_id="42"),
    )
    new_namespace = _make_namespace(
        "ci-new",
        base_time + timedelta(minutes=1),
        labels=_ci_labels(branch="feature-b", mr_id="42"),
    )
    collect_controller.config.namespaces = [
        CollectNamespaceConfig(
            names=["ci-*"], checks=CheckOptions(superseded=True)
        )
    ]
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[old_namespace, new_namespace]
    )
    collect_controller.patch_namespace = MagicMock()

    collect_controller.check_superseded_namespaces()

    collect_controller.patch_namespace.assert_called_once()
    assert collect_controller.patch_namespace.call_args.args == ("ci-old",)
    annotations = collect_controller.patch_namespace.call_args.kwargs[
        "annotations"
    ]
    assert (
        annotations[NamespaceAnnotations.STATUS.value]
        == NamespaceStatus.SUPERSEDED.value
    )
    assert NamespaceAnnotations.STATUS_TS.value in annotations
    assert annotations[NamespaceAnnotations.NOTIFIED_TS.value] is None
    assert annotations[NamespaceAnnotations.NOTIFIED_STATUS.value] is None


def test_check_superseded_namespaces_groups_by_branch(collect_controller):
    """Namespaces without MR labels should group by project and branch."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    old_namespace = _make_namespace(
        "ci-old", base_time, labels=_ci_labels(branch="main")
    )
    new_namespace = _make_namespace(
        "ci-new",
        base_time + timedelta(minutes=1),
        labels=_ci_labels(branch="main"),
    )
    collect_controller.config.namespaces = [
        CollectNamespaceConfig(
            names=["ci-*"], checks=CheckOptions(superseded=True)
        )
    ]
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[old_namespace, new_namespace]
    )
    collect_controller.patch_namespace = MagicMock()

    collect_controller.check_superseded_namespaces()

    collect_controller.patch_namespace.assert_called_once()
    assert collect_controller.patch_namespace.call_args.args == ("ci-old",)


def test_check_superseded_namespaces_is_opt_in(collect_controller):
    """Superseded detection should do nothing unless checks enable it."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    collect_controller.config.namespaces = [
        CollectNamespaceConfig(names=["ci-*"])
    ]
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[
            _make_namespace("ci-old", base_time, labels=_ci_labels()),
            _make_namespace(
                "ci-new",
                base_time + timedelta(minutes=1),
                labels=_ci_labels(),
            ),
        ]
    )
    collect_controller.patch_namespace = MagicMock()

    collect_controller.check_superseded_namespaces()

    collect_controller.patch_namespace.assert_not_called()


def test_check_superseded_namespaces_keeps_newest(collect_controller):
    """Only the newest namespace in a CI group should remain current."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    collect_controller.config.namespaces = [
        CollectNamespaceConfig(
            names=["ci-*"], checks=CheckOptions(superseded=True)
        )
    ]
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[
            _make_namespace("ci-old", base_time, labels=_ci_labels()),
            _make_namespace(
                "ci-middle",
                base_time + timedelta(minutes=1),
                labels=_ci_labels(),
            ),
            _make_namespace(
                "ci-new",
                base_time + timedelta(minutes=2),
                labels=_ci_labels(),
            ),
        ]
    )
    collect_controller.patch_namespace = MagicMock()

    collect_controller.check_superseded_namespaces()

    assert [
        call.args[0]
        for call in collect_controller.patch_namespace.call_args_list
    ] == ["ci-old", "ci-middle"]


def test_check_superseded_namespaces_skips_missing_labels(
    collect_controller,
):
    """Namespaces missing CI identity labels should not be grouped."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    collect_controller.config.namespaces = [
        CollectNamespaceConfig(
            names=["ci-*"], checks=CheckOptions(superseded=True)
        )
    ]
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[
            _make_namespace("ci-missing-project", base_time, labels={}),
            _make_namespace(
                "ci-missing-branch",
                base_time + timedelta(minutes=1),
                labels=_ci_labels(branch=None),
            ),
        ]
    )
    collect_controller.patch_namespace = MagicMock()

    collect_controller.check_superseded_namespaces()

    collect_controller.patch_namespace.assert_not_called()


def test_check_superseded_namespaces_patches_older_active_only(
    collect_controller,
):
    """Only older active namespaces should be patched as superseded."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    collect_controller.config.namespaces = [
        CollectNamespaceConfig(
            names=["ci-*"], checks=CheckOptions(superseded=True)
        )
    ]
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[
            _make_namespace("ci-old", base_time, labels=_ci_labels()),
            _make_namespace(
                "ci-terminating",
                base_time + timedelta(seconds=30),
                labels=_ci_labels(),
                phase="Terminating",
            ),
            _make_namespace(
                "ci-cancelled",
                base_time + timedelta(seconds=45),
                labels=_ci_labels(),
                annotations={
                    NamespaceAnnotations.STATUS.value: (
                        NamespaceStatus.CANCELLED.value
                    )
                },
            ),
            _make_namespace(
                "ci-new",
                base_time + timedelta(minutes=1),
                labels=_ci_labels(),
            ),
        ]
    )
    collect_controller.patch_namespace = MagicMock()

    collect_controller.check_superseded_namespaces()

    assert [
        call.args[0]
        for call in collect_controller.patch_namespace.call_args_list
    ] == ["ci-old"]


def test_get_collect_controller_pods(collect_controller):
    """Replica discovery should only include active collect-controller pods."""
    collect_controller.config.context.stateful_set_name = None
    collect_controller.get_namespace_pods_by = MagicMock(
        return_value=[
            _make_pod("collect-1", "collect-ctl-sa"),
            _make_pod("collect-2", "collect-ctl-sa"),
            _make_pod("other", "other-sa"),
            _make_pod("terminating", "collect-ctl-sa", deleting=True),
        ]
    )

    assert collect_controller._get_collect_controller_pods() == [
        "collect-1",
        "collect-2",
    ]


def test_reconcile_metrics_files_filters_active_app_components(
    collect_controller,
):
    """Metrics reconciliation should target active namespace-manager pods."""
    instance_label = {
        "app.kubernetes.io/instance": "ska-ser-namespace-manager",
    }
    collect_controller.get_namespace_pods_by = MagicMock(
        return_value=[
            _make_pod(
                "api-1",
                "api-sa",
                labels={
                    **instance_label,
                    "app.kubernetes.io/component": "api",
                },
            ),
            _make_pod(
                "collect-1",
                "collect-ctl-sa",
                labels={
                    **instance_label,
                    "app.kubernetes.io/component": "collect-controller",
                },
            ),
            _make_pod(
                "action-1",
                "action-sa",
                labels={
                    **instance_label,
                    "app.kubernetes.io/component": "action-controller",
                },
            ),
            _make_pod(
                "terminating",
                "collect-ctl-sa",
                deleting=True,
                labels={
                    **instance_label,
                    "app.kubernetes.io/component": "collect-controller",
                },
            ),
            _make_pod(
                "unrelated-component",
                "other-sa",
                labels={
                    **instance_label,
                    "app.kubernetes.io/component": "other",
                },
            ),
            _make_pod(
                "missing-component",
                "other-sa",
                labels=instance_label,
            ),
        ]
    )
    collect_controller.config.metrics.enabled = True
    collect_controller.leader_lock.is_leader.return_value = True
    collect_controller.metrics_manager = MagicMock()

    collect_controller.reconcile_metrics_files()

    collect_controller.get_namespace_pods_by.assert_called_once_with(
        namespace="default-namespace",
        labels={"app.kubernetes.io/instance": "ska-ser-namespace-manager"},
    )
    delete_metrics_files = (
        collect_controller.metrics_manager.delete_stale_metrics_files
    )
    delete_metrics_files.assert_called_once_with(
        ["action-1", "api-1", "collect-1"]
    )


def test_get_collect_controller_pods_from_stateful_set(collect_controller):
    """StatefulSet ordinal pod names should drive replica discovery."""
    stateful_set = MagicMock()
    stateful_set.spec.replicas = 3
    collect_controller.config.context.stateful_set_name = "collect-controller"
    collect_controller.get_namespaced_stateful_set = MagicMock(
        return_value=stateful_set
    )
    collect_controller.get_namespace_pods_by = MagicMock()

    assert collect_controller._get_collect_controller_pods() == [
        "collect-controller-0",
        "collect-controller-1",
        "collect-controller-2",
    ]
    collect_controller.get_namespace_pods_by.assert_not_called()


def test_get_collect_controller_pods_falls_back_to_live_pods(
    collect_controller,
):
    """Live pod discovery should be used if the StatefulSet is unavailable."""
    collect_controller.config.context.stateful_set_name = "collect-controller"
    collect_controller.get_namespaced_stateful_set = MagicMock(
        return_value=None
    )
    collect_controller.get_namespace_pods_by = MagicMock(
        return_value=[
            _make_pod("collect-1", "collect-ctl-sa"),
            _make_pod("collect-2", "collect-ctl-sa"),
        ]
    )

    assert collect_controller._get_collect_controller_pods() == [
        "collect-1",
        "collect-2",
    ]


def test_get_assigned_managed_namespaces(collect_controller):
    """Shard assignment should deterministically select this replica share."""
    namespaces = []
    for name in ["a", "b", "c", "d"]:
        namespace = MagicMock()
        namespace.metadata.name = name
        namespaces.append(namespace)

    collect_controller._get_collect_controller_pods = MagicMock(
        return_value=["collect-1", "collect-2"]
    )

    assigned = collect_controller._get_assigned_managed_namespaces(namespaces)

    assert [namespace.metadata.name for namespace in assigned] == [
        namespace.metadata.name
        for namespace in namespaces
        if (
            int(
                hashlib.sha256(
                    namespace.metadata.name.encode("utf-8")
                ).hexdigest(),
                16,
            )
            % 2
        )
        == 0
    ]


def test_get_assigned_managed_namespaces_uses_expected_ordinals(
    collect_controller,
):
    """Missing live pods should not collapse assignments to active replicas."""
    collect_controller.current_pod_name = "collect-controller-0"
    stateful_set = MagicMock()
    stateful_set.spec.replicas = 2
    collect_controller.config.context.stateful_set_name = "collect-controller"
    collect_controller.get_namespaced_stateful_set = MagicMock(
        return_value=stateful_set
    )
    collect_controller.get_namespace_pods_by = MagicMock(
        return_value=[_make_pod("collect-controller-0", "collect-ctl-sa")]
    )
    namespaces = []
    for name in ["a", "b", "c", "d"]:
        namespace = MagicMock()
        namespace.metadata.name = name
        namespaces.append(namespace)

    assigned = collect_controller._get_assigned_managed_namespaces(namespaces)

    assert [namespace.metadata.name for namespace in assigned] == [
        namespace.metadata.name
        for namespace in namespaces
        if (
            int(
                hashlib.sha256(
                    namespace.metadata.name.encode("utf-8")
                ).hexdigest(),
                16,
            )
            % 2
        )
        == 0
    ]
    collect_controller.get_namespace_pods_by.assert_not_called()


def test_get_assigned_managed_namespaces_current_pod_outside_ordinals(
    collect_controller,
):
    """No namespaces should be assigned outside the expected ordinal set."""
    collect_controller.current_pod_name = "collect-controller-random"
    stateful_set = MagicMock()
    stateful_set.spec.replicas = 2
    collect_controller.config.context.stateful_set_name = "collect-controller"
    collect_controller.get_namespaced_stateful_set = MagicMock(
        return_value=stateful_set
    )
    namespace = MagicMock()
    namespace.metadata.name = "a"

    assert (
        collect_controller._get_assigned_managed_namespaces([namespace]) == []
    )


def test_get_assigned_managed_namespaces_current_pod_missing(
    collect_controller,
):
    """No namespaces should be assigned if the current pod is unknown."""
    collect_controller._get_collect_controller_pods = MagicMock(
        return_value=["collect-2", "collect-3"]
    )

    assert collect_controller._get_assigned_managed_namespaces([]) == []


def test_get_namespace_check_period(collect_controller):
    """Threaded namespace checks should parse interval schedules."""
    namespace_config = MagicMock()
    namespace_config.actions = {
        CollectActions.CHECK_NAMESPACE: MagicMock(schedule="45s")
    }

    assert collect_controller._get_namespace_check_period(
        namespace_config
    ) == timedelta(seconds=45)


def test_get_namespace_check_period_invalid(collect_controller):
    """Invalid schedules should fall back to the default interval."""
    namespace_config = MagicMock()
    namespace_config.actions = {
        CollectActions.CHECK_NAMESPACE: MagicMock(schedule="invalid")
    }

    assert collect_controller._get_namespace_check_period(
        namespace_config
    ) == timedelta(seconds=60)


def test_get_namespace_thread_name(collect_controller):
    """Namespace thread names should be stable and unique."""
    assert (
        collect_controller._get_namespace_thread_name("test-namespace")
        == "namespace-check-test-namespace"
    )


def test_run_namespace_check_uses_shared_collector(collect_controller):
    """Namespace checks should reuse the controller's collector instance."""
    collect_controller.run_namespace_check("test-namespace")

    collect_controller.namespace_collector.run_action.assert_called_once_with(
        CollectActions.CHECK_NAMESPACE,
        "test-namespace",
        None,
    )


def test_create_namespace_check_thread(collect_controller):
    """Newly assigned namespaces should create one managed thread."""
    collect_controller.add_managed_task = MagicMock()
    collect_controller.has_task = MagicMock(return_value=False)

    collect_controller.create_namespace_check_thread(
        "test-namespace", timedelta(seconds=30)
    )

    collect_controller.add_managed_task.assert_called_once()
    assert collect_controller.namespace_check_threads == {
        "test-namespace": "namespace-check-test-namespace"
    }


def test_create_namespace_check_thread_skips_existing(
    collect_controller,
):
    """Existing namespace threads should not be recreated."""
    collect_controller.add_managed_task = MagicMock()
    collect_controller.has_task = MagicMock(return_value=True)

    collect_controller.create_namespace_check_thread(
        "test-namespace", timedelta(seconds=30)
    )

    collect_controller.add_managed_task.assert_not_called()


def test_remove_namespace_check_thread(collect_controller):
    """Unassigned namespaces should have their threads removed."""
    collect_controller.namespace_check_threads = {
        "test-namespace": "namespace-check-test-namespace"
    }
    collect_controller.remove_task = MagicMock()

    collect_controller.remove_namespace_check_thread("test-namespace")

    collect_controller.remove_task.assert_called_once_with(
        "namespace-check-test-namespace"
    )
    assert collect_controller.namespace_check_threads == {}


def test_remove_namespace_check_thread_missing(collect_controller):
    """Removing a missing namespace thread should be a no-op."""
    collect_controller.has_task = MagicMock(return_value=False)
    collect_controller.remove_task = MagicMock()

    collect_controller.remove_namespace_check_thread("missing")

    collect_controller.remove_task.assert_not_called()


def test_check_assigned_namespaces_creates_new_thread(collect_controller):
    """Assigned namespaces should create one periodic thread each."""
    namespace = MagicMock()
    namespace.metadata.name = "test-namespace"
    namespace.metadata.annotations = {}
    namespace_config = MagicMock()
    namespace_config.actions = {
        CollectActions.CHECK_NAMESPACE: MagicMock(schedule="30s")
    }
    collect_controller.get_namespaces_by = MagicMock(return_value=[namespace])
    collect_controller._get_assigned_managed_namespaces = MagicMock(
        return_value=[namespace]
    )
    collect_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={},
        )
    )
    collect_controller.create_namespace_check_thread = MagicMock()
    collect_controller.namespace_check_threads = {}

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=namespace_config,
    ):
        collect_controller.check_assigned_namespaces()

    collect_controller.create_namespace_check_thread.assert_called_once_with(
        "test-namespace", timedelta(seconds=30)
    )
    assert Path(collect_controller.config.heartbeat.path).exists()


def test_check_assigned_namespaces_reuses_existing_thread(
    collect_controller,
):
    """Reconciliation should not duplicate an existing namespace thread."""
    namespace = MagicMock()
    namespace.metadata.name = "test-namespace"
    namespace.metadata.annotations = {}
    collect_controller.get_namespaces_by = MagicMock(return_value=[namespace])
    collect_controller._get_assigned_managed_namespaces = MagicMock(
        return_value=[namespace]
    )
    collect_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={},
        )
    )
    collect_controller.create_namespace_check_thread = MagicMock()
    collect_controller.namespace_check_threads = {
        "test-namespace": "namespace-check-test-namespace"
    }

    with patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=MagicMock(
            actions={CollectActions.CHECK_NAMESPACE: MagicMock(schedule="30s")}
        ),
    ):
        collect_controller.check_assigned_namespaces()

    collect_controller.create_namespace_check_thread.assert_called_once()
    assert Path(collect_controller.config.heartbeat.path).exists()


def test_check_assigned_namespaces_removes_unassigned_thread(
    collect_controller,
):
    """Reconciliation should remove threads no longer assigned here."""
    collect_controller.get_namespaces_by = MagicMock(return_value=[])
    collect_controller._get_assigned_managed_namespaces = MagicMock(
        return_value=[]
    )
    collect_controller.namespace_check_threads = {
        "test-namespace": "namespace-check-test-namespace"
    }
    collect_controller.remove_namespace_check_thread = MagicMock()

    collect_controller.check_assigned_namespaces()

    collect_controller.remove_namespace_check_thread.assert_called_once_with(
        "test-namespace"
    )
    assert Path(collect_controller.config.heartbeat.path).exists()


def test_check_assigned_namespaces_updates_heartbeat_without_assignments(
    collect_controller,
):
    """Heartbeat should still refresh when nothing is assigned."""
    collect_controller.get_namespaces_by = MagicMock(return_value=[])
    collect_controller._get_assigned_managed_namespaces = MagicMock(
        return_value=[]
    )

    collect_controller.check_assigned_namespaces()

    assert Path(collect_controller.config.heartbeat.path).exists()


def test_check_assigned_namespaces_updates_heartbeat_without_peers(
    collect_controller,
):
    """Heartbeat should still refresh when peer discovery returns none."""
    collect_controller.get_namespaces_by = MagicMock(return_value=[])
    collect_controller._get_collect_controller_pods = MagicMock(
        return_value=[]
    )

    collect_controller.check_assigned_namespaces()

    assert Path(collect_controller.config.heartbeat.path).exists()


def test_generate_metrics_updates_assigned_namespaces(collect_controller):
    """
    Metrics generation should only write this replica's assigned namespaces.
    """
    assigned_namespace = MagicMock()
    assigned_namespace.metadata.name = "assigned-namespace"
    assigned_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value
    }
    unassigned_namespace = MagicMock()
    unassigned_namespace.metadata.name = "unassigned-namespace"
    unassigned_namespace.metadata.annotations = {
        NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILING.value
    }
    collect_controller.config.metrics.enabled = True
    collect_controller.get_namespaces_by = MagicMock(
        return_value=[assigned_namespace, unassigned_namespace]
    )
    collect_controller._get_assigned_managed_namespaces = MagicMock(
        return_value=[assigned_namespace]
    )
    collect_controller.metrics_manager = MagicMock()

    collect_controller.generate_metrics()

    collect_controller.metrics_manager.delete_stale_metrics.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        ["assigned-namespace"]
    )
    collect_controller.metrics_manager.update_namespace_metrics.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        assigned_namespace
    )
    collect_controller.metrics_manager.save_metrics.assert_called_once_with()


def test_reconcile_metrics_files_deletes_files_for_inactive_pods(
    collect_controller,
):
    """Metrics reconciliation should keep files for active pods only."""
    collect_controller.get_namespace_pods_by = MagicMock(
        return_value=[
            _make_pod(
                "api-1",
                "api-sa",
                labels={"app.kubernetes.io/component": "api"},
            ),
            _make_pod(
                "collect-1",
                "collect-ctl-sa",
                labels={"app.kubernetes.io/component": "collect-controller"},
            ),
            _make_pod(
                "action-1",
                "action-sa",
                labels={"app.kubernetes.io/component": "action-controller"},
            ),
        ]
    )
    collect_controller.config.metrics.enabled = True
    collect_controller.leader_lock.is_leader.return_value = True
    collect_controller.metrics_manager = MagicMock()

    collect_controller.reconcile_metrics_files()

    delete_metrics_files = (
        collect_controller.metrics_manager.delete_stale_metrics_files
    )
    delete_metrics_files.assert_called_once_with(
        ["action-1", "api-1", "collect-1"]
    )


def test_reconcile_metrics_files_skips_when_no_active_pods(
    collect_controller, caplog
):
    """Metrics reconciliation should not delete files without pod data."""
    collect_controller.get_namespace_pods_by = MagicMock(return_value=[])
    collect_controller.config.metrics.enabled = True
    collect_controller.leader_lock.is_leader.return_value = True
    collect_controller.metrics_manager = MagicMock()

    collect_controller.reconcile_metrics_files()

    delete_metrics_files = (
        collect_controller.metrics_manager.delete_stale_metrics_files
    )
    delete_metrics_files.assert_not_called()
    assert (
        "Skipping metrics file reconciliation because no active "
        "namespace-manager pods were discovered"
    ) in caplog.text


def test_update_heartbeat_refreshes_mtime(collect_controller):
    """Heartbeat updates should refresh the file modification time."""
    heartbeat_path = Path(collect_controller.config.heartbeat.path)

    collect_controller._update_heartbeat()
    initial_mtime = heartbeat_path.stat().st_mtime_ns
    time.sleep(0.01)
    collect_controller._update_heartbeat()

    assert heartbeat_path.stat().st_mtime_ns > initial_mtime


def test_check_assigned_namespaces_continues_when_heartbeat_write_fails(
    collect_controller, caplog
):
    """Heartbeat write failures should be logged without stopping work."""
    namespace = MagicMock()
    namespace.metadata.name = "test-namespace"
    namespace.metadata.annotations = {}
    namespace_config = MagicMock()
    namespace_config.actions = {
        CollectActions.CHECK_NAMESPACE: MagicMock(schedule="30s")
    }
    collect_controller.get_namespaces_by = MagicMock(return_value=[namespace])
    collect_controller._get_assigned_managed_namespaces = MagicMock(
        return_value=[namespace]
    )
    collect_controller.to_dto = MagicMock(
        return_value=Namespace(
            name="test-namespace",
            labels={},
            annotations={},
        )
    )
    collect_controller.create_namespace_check_thread = MagicMock()

    with patch.object(Path, "touch", side_effect=OSError("disk full")), patch(
        "ska_ser_namespace_manager.controller.collect_controller.match_namespace",  # pylint: disable=line-too-long # noqa: E501
        return_value=namespace_config,
    ):
        collect_controller.check_assigned_namespaces()

    assert "Failed to update collect-controller heartbeat" in caplog.text
    collect_controller.create_namespace_check_thread.assert_called_once_with(
        "test-namespace", timedelta(seconds=30)
    )


def test_namespace_thread_stops_when_namespace_missing(
    collect_controller,
):
    """Per-namespace threads should exit when the namespace disappears."""
    collect_controller.has_task = MagicMock(return_value=False)
    collect_controller.get_namespace = MagicMock(return_value=None)
    collect_controller.run_namespace_check = MagicMock()
    collect_controller.metrics_manager = MagicMock()
    collect_controller.add_managed_task = MagicMock()

    collect_controller.create_namespace_check_thread(
        "test-namespace", timedelta(milliseconds=1)
    )

    task = collect_controller.add_managed_task.call_args.args[1]
    task_args = collect_controller.add_managed_task.call_args.args[2]
    stop_event = threading.Event()
    task(stop_event, *task_args)

    collect_controller.run_namespace_check.assert_not_called()
    record_result = (
        collect_controller.metrics_manager.record_namespace_check_result
    )
    record_result.assert_not_called()


def test_namespace_thread_records_successful_check(
    collect_controller,
):
    """Successful per-namespace checks should record a success result."""
    namespace_resource = MagicMock()
    stop_event = threading.Event()
    collect_controller.get_namespace = MagicMock(
        return_value=namespace_resource
    )
    collect_controller.run_namespace_check = MagicMock()
    collect_controller.metrics_manager = MagicMock()
    collect_controller.wait_for_task_stop = MagicMock(return_value=True)

    collect_controller.run_namespace_check_thread(
        stop_event, "test-namespace", timedelta(milliseconds=1)
    )

    collect_controller.run_namespace_check.assert_called_once_with(
        "test-namespace", namespace_resource
    )
    collect_controller.metrics_manager.record_namespace_check_result.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        "success"
    )


def test_namespace_thread_records_failed_check(collect_controller, caplog):
    """Failed per-namespace checks should record a failure result."""
    namespace_resource = MagicMock()
    stop_event = threading.Event()
    collect_controller.get_namespace = MagicMock(
        return_value=namespace_resource
    )
    collect_controller.run_namespace_check = MagicMock(
        side_effect=RuntimeError("collector failed")
    )
    collect_controller.metrics_manager = MagicMock()
    collect_controller.wait_for_task_stop = MagicMock(return_value=True)

    collect_controller.run_namespace_check_thread(
        stop_event, "test-namespace", timedelta(milliseconds=1)
    )

    collect_controller.run_namespace_check.assert_called_once_with(
        "test-namespace", namespace_resource
    )
    collect_controller.metrics_manager.record_namespace_check_result.assert_called_once_with(  # pylint: disable=line-too-long # noqa: E501
        "failure"
    )
    assert (
        "Namespace check thread failed for namespace 'test-namespace'"
        in caplog.text
    )
