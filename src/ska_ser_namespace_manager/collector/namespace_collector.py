"""
namespace_collector checks Kubernetes namespaces
for staleness and failures
"""

import traceback
from datetime import datetime, timezone
from typing import Callable, Dict, List

import pytz
from dateutil.parser import parse

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.utils import now


class NamespaceCollector(Collector):
    """
    NamespaceCollector checks namespaces for staleness and failures
    periodically. The inferred status is stored in the form of
    annotations in the namespace itself
    """

    @classmethod
    def get_actions(cls) -> Dict[CollectActions, Callable]:
        """
        Returns the possible actions for this collector

        :return: Dict of actions for this collector
        """
        return {CollectActions.CHECK_NAMESPACE: cls.check_namespace}

    def set_status(self, annotations: Dict[str, str], status: str) -> None:
        """
        Set the status and status timestamp in the annotations.

        :param annotations: The annotations to update
        :param status: The status to set
        """
        if annotations.get("manager.cicd.skao.int/status", None) == status:
            logging.info(
                "Namespace %s status is already set to %s",
                self.namespace,
                status,
            )
            return

        annotations["manager.cicd.skao.int/status"] = status
        annotations["manager.cicd.skao.int/status_timestamp"] = now()
        logging.info(
            "Setting namespace '%s' status: %s",
            self.namespace,
            status,
        )
        self.patch_namespace(self.namespace, annotations=annotations)

    def check_stale(
        self, annotations: Dict[str, str], creation_timestamp: datetime
    ) -> bool:
        """
        Check if the namespace is stale based on the TTL

        :param annotations: The annotations to check
        :param creation_timestamp: Namespace creation timestamp
        :return: True if namespace was stale, False otherwise
        """
        if self.namespace_config.ttl is None:
            return False

        creation_timestamp = creation_timestamp.replace(tzinfo=timezone.utc)
        is_stale = (
            datetime.now(pytz.UTC) - creation_timestamp
            >= self.namespace_config.ttl
        )
        if is_stale:
            self.set_status(annotations, "stale")

        return is_stale

    def _is_after_grace_period(self, annotations: Dict[str, str]) -> bool:
        current_time = now()
        status_timestamp = parse(
            annotations.get(
                "manager.cicd.skao.int/status_timestamp", current_time
            )
        ).replace(tzinfo=None)
        grace_time = status_timestamp + self.namespace_config.grace_period
        logging.debug(
            "Status Timestamp: %s; Grace Timestamp: %s",
            status_timestamp,
            grace_time,
        )
        return grace_time < parse(current_time).replace(tzinfo=None)

    def _check_resource_status(
        self, namespace: str, resource_type: str
    ) -> List[str]:
        """
        Check if any resources of the given type in the specified namespace
        have errors.

        :param namespace: The namespace to check.
        :param resource_type: The type of resource to check
        ('deployment', 'statefulset', 'daemonset', 'replicaset').
        :return: List of names of failing resources.
        """
        failing_resources = []

        try:
            if resource_type == "deployment":
                res = self.apps_v1.list_namespaced_deployment(namespace)
            elif resource_type == "statefulset":
                res = self.apps_v1.list_namespaced_stateful_set(namespace)
            elif resource_type == "daemonset":
                res = self.apps_v1.list_namespaced_daemon_set(namespace)
            elif resource_type == "replicaset":
                res = self.apps_v1.list_namespaced_replica_set(namespace)
            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

            for resource in res.items:
                available_replicas = resource.status.available_replicas or 0
                desired_replicas = resource.status.replicas or 0
                if available_replicas < desired_replicas:
                    failing_resources.append(resource.metadata.name)
                    logging.warning(
                        "Namespace %s has a %s %s which has "
                        "less replicas than desired.",
                        namespace,
                        resource_type,
                        resource.metadata.name,
                    )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Exception when retrieving %s: %s", resource_type, exc
            )
            traceback.print_exception(exc)

        return failing_resources

    def check_failure(self, annotations: Dict[str, str]) -> bool:
        """
        Check if there are failures in Deployment, ReplicaSet,
        StatefulSet or DaemonSet and manage status annotations.

        :param annotations: Annotations to consider.
        :return: True if there are failures, False otherwise.
        """
        old_failing_resources = set(
            filter(
                None,
                annotations.get(
                    "manager.cicd.skao.int/failing_resources", ""
                ).split(","),
            )
        )

        deployments = self._check_resource_status(self.namespace, "deployment")
        statefulsets = self._check_resource_status(
            self.namespace, "statefulset"
        )
        daemonsets = self._check_resource_status(self.namespace, "daemonset")

        new_failing_resources = set(deployments + statefulsets + daemonsets)

        annotations["manager.cicd.skao.int/failing_resources"] = ",".join(
            new_failing_resources
        )

        if old_failing_resources.intersection(
            new_failing_resources
        ) and self._is_after_grace_period(annotations):
            self.set_status(annotations, "failed")
        elif old_failing_resources.intersection(
            new_failing_resources
        ) and not self._is_after_grace_period(annotations):
            self.set_status(annotations, "failing")
        elif (
            new_failing_resources
            and not old_failing_resources
            and not self._is_after_grace_period(annotations)
        ):
            self.set_status(annotations, "failing")
        elif new_failing_resources and old_failing_resources:
            self.set_status(annotations, "unstable")

        return bool(new_failing_resources)

    def check_namespace(self) -> None:
        """
        Check the namespace for staleness and failures.
        """
        logging.info("Starting check for namespace '%s'", self.namespace)
        namespace = self.get_namespace(self.namespace)
        if namespace is None:
            logging.error("Failed to get namespace '%s'", self.namespace)
            return

        annotations = namespace.metadata.annotations or {}
        running = not (
            self.check_stale(
                annotations, namespace.metadata.creation_timestamp
            )
            or self.check_failure(annotations)
        )

        if running:
            self.set_status(annotations, "ok")

        logging.debug("Completed check for namespace: '%s", self.namespace)
