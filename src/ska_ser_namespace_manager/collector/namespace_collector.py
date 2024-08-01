"""
namespace_collector checks Kubernetes namespaces
for staleness and failures
"""

from datetime import datetime, timezone
from typing import Callable, Dict

import pytz

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)
from ska_ser_namespace_manager.core.logging import logging


def now() -> str:
    """
    Gets now date as UTC in ISO8601 format
    """
    return datetime.now(pytz.UTC).isoformat().replace("+00:00", "Z")


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

    # def _has_pod_errors(self, pod) -> bool:
    #     """
    #     Check if a pod has errors in its container statuses.

    #     :param pod: The pod to check.
    #     :type pod: V1Pod
    #     :return: True if the pod has errors, False otherwise.
    #     :rtype: bool
    #     """
    #     for container_status in pod.status.container_statuses:
    #         container_name = container_status.name
    #         state = container_status.state
    #         if state.waiting and state.waiting.reason in [
    #             "ImagePullBackOff",
    #             "ErrImagePull",
    #         ]:
    #             self.logger.info(
    #                 "  Container: %s, Error: %s, Message: %s",
    #                 container_name,
    #                 state.waiting.reason,
    #                 state.waiting.message,
    #             )
    #             return True
    #     return False

    # def check_failure(self, annotations: Dict[str, str]) -> None:
    #     """
    #     Check for failures in the namespace.

    #     :param annotations: The annotations to update.
    #     :type annotations: Dict[str, str]
    #     """
    #     self.logger.debug(
    #         "Checking for failures in namespace: %s", self.namespace_str
    #     )

    #     try:
    #         pods = self.get_pods_from_namespace(self.namespace_str)
    #     except ApiException as e:
    #         self.logger.error(
    #             "Failed to list pods in namespace %s: %s",
    #             self.namespace_str,
    #             e,
    #         )
    #         return

    #     has_errors = False
    #     for pod in pods:
    #         pod_status = pod.status.phase
    #         # NOTE: should we check Pending, Failure and Unknown?
    #         if pod_status == "Pending":
    #             self.logger.info(
    #                 "Pod: %s, Status: %s", pod.metadata.name, pod_status
    #             )
    #             has_errors = self._has_pod_errors(pod)

    #     current_time = datetime.utcnow().replace(tzinfo=None)
    #     status = annotations.get("cicd.skao.int/status", "not_checked")
    #     status_timestamp = parse(
    #         annotations.get(
    #             "cicd.skao.int/status_timestamp",
    #             current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    #         )
    #     ).replace(tzinfo=None)

    #     grace_time = status_timestamp + timedelta(seconds=self.grace_period)

    #     if has_errors:
    #         self.logger.debug(
    #             "Errors detected in namespace: %s", self.namespace_str
    #         )

    #         if status in ["not_checked", "running"]:
    #             self.set_status(annotations, "failing")

    #         elif status == "failing" and grace_time < current_time:
    #             self.set_status(annotations, "failed")

    #     elif not has_errors and status == "not_checked":
    #         self.logger.info(
    #             "No errors detected in namespace: '%s", self.namespace_str
    #         )
    #         self.set_status(annotations, "running")

    def check_namespace(self) -> None:
        """
        Check the namespace for staleness and failures.
        """
        logging.debug("Starting check for namespace '%s'", self.namespace)
        namespace = self.get_namespace(self.namespace)
        if namespace is None:
            logging.error("Failed to get namespace '%s'", self.namespace)
            return

        annotations = namespace.metadata.annotations
        if annotations is None:
            annotations = {}

        is_stale = self.check_stale(
            annotations, namespace.metadata.creation_timestamp
        )
        # self.check_failure(annotations)
        if not is_stale:
            self.set_status(annotations, "ok")

        logging.debug("Completed check for namespace: '%s", self.namespace)
