"""
sharding provides deterministic namespace-to-replica assignment helpers
"""

import hashlib
from typing import Iterable, List

from kubernetes import client


def is_pod_ready(pod: client.V1Pod) -> bool:
    """
    Return whether a pod is in a ready running state.
    """
    if pod.status is None or pod.status.phase != "Running":
        return False

    conditions = pod.status.conditions or []
    return any(
        condition.type == "Ready" and condition.status == "True"
        for condition in conditions
    )


class NamespaceShardAssigner:
    """
    NamespaceShardAssigner maps namespaces to replicas using a highest-score
    hash so that replica membership changes only reassign affected namespaces.
    """

    @staticmethod
    def _score(namespace: str, replica_id: str) -> int:
        digest = hashlib.sha256(
            f"{namespace}:{replica_id}".encode("utf-8")
        ).hexdigest()
        return int(digest, 16)

    @classmethod
    def get_owner_replica(
        cls, namespace: str, replica_ids: Iterable[str]
    ) -> str | None:
        """
        Return the replica that owns the namespace for a given membership set.
        """
        replicas = sorted(replica_ids)
        if len(replicas) == 0:
            return None

        return max(replicas, key=lambda replica_id: cls._score(namespace, replica_id))

    @classmethod
    def owns_namespace(
        cls, namespace: str, replica_id: str, replica_ids: Iterable[str]
    ) -> bool:
        """
        Return whether the given replica owns the namespace.
        """
        return cls.get_owner_replica(namespace, replica_ids) == replica_id


def get_ready_pod_names(pods: List[client.V1Pod]) -> List[str]:
    """
    Return sorted ready pod names from a pod list.
    """
    return sorted(
        pod.metadata.name
        for pod in pods
        if pod.metadata is not None
        and pod.metadata.name
        and is_pod_ready(pod)
    )
