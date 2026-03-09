from unittest.mock import MagicMock

from ska_ser_namespace_manager.controller.sharding import (
    NamespaceShardAssigner,
    get_ready_pod_names,
    is_pod_ready,
)


def test_is_pod_ready_true():
    pod = MagicMock()
    pod.status.phase = "Running"
    pod.status.conditions = [MagicMock(type="Ready", status="True")]

    assert is_pod_ready(pod) is True


def test_is_pod_ready_false():
    pod = MagicMock()
    pod.status.phase = "Pending"
    pod.status.conditions = [MagicMock(type="Ready", status="False")]

    assert is_pod_ready(pod) is False


def test_get_ready_pod_names():
    ready_b = MagicMock()
    ready_b.metadata.name = "collect-b"
    ready_b.status.phase = "Running"
    ready_b.status.conditions = [MagicMock(type="Ready", status="True")]

    ready_a = MagicMock()
    ready_a.metadata.name = "collect-a"
    ready_a.status.phase = "Running"
    ready_a.status.conditions = [MagicMock(type="Ready", status="True")]

    not_ready = MagicMock()
    not_ready.metadata.name = "collect-c"
    not_ready.status.phase = "Pending"
    not_ready.status.conditions = [MagicMock(type="Ready", status="False")]

    assert get_ready_pod_names([ready_b, not_ready, ready_a]) == [
        "collect-a",
        "collect-b",
    ]


def test_namespace_shard_assigner_is_deterministic():
    replicas = ["collect-a", "collect-b", "collect-c"]

    owner = NamespaceShardAssigner.get_owner_replica("ci-test", replicas)

    assert owner in replicas
    assert (
        NamespaceShardAssigner.get_owner_replica("ci-test", replicas) == owner
    )
    assert NamespaceShardAssigner.owns_namespace("ci-test", owner, replicas)
