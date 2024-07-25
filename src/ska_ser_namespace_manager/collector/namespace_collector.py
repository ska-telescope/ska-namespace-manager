"""
This module provides the NamespaceCollector class for checking Kubernetes
namespaces for staleness and failures.

The NamespaceCollector class checks if a namespace is stale based on a
configured TTL and also checks for pod failures such as ImagePullBackOff
errors. The results are updated in the namespace annotations.

Classes:
    NamespaceCollector: A class to check Kubernetes namespaces for
    staleness and failures.

Functions:
    main: Main function to parse arguments and run the specified action.

Usage:
    To use this module, create an instance of NamespaceCollector and call
    the check_namespace() method.
    Example:
        checker = NamespaceCollector(namespace)
        checker.check_namespace()
"""

import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict

from dateutil.parser import parse
from kubernetes.client.rest import ApiException

from ska_ser_namespace_manager.core.k8s import KubernetesAPI
from ska_ser_namespace_manager.core.logging import logging


class NamespaceCollector(KubernetesAPI):
    """
    A class to check Kubernetes namespaces for staleness and failures.

    This class periodically checks if a namespace is stale based on a
    configured TTL and also checks for pod failures such as ImagePullBackOff
    errors. The results are updated in the namespace annotations.
    """

    def __init__(self, namespace: str, kubeconfig_path=None) -> None:
        """
        Initialize NamespaceCollector with the provided namespace.

        :param namespace: The name of the namespace to check.
        :type namespace: str
        """
        super().__init__(kubeconfig_path=kubeconfig_path)
        self.logger = logging.getLogger(__name__)
        self.namespace_str = namespace
        self.ttl = int(os.getenv("NAMESPACE_TTL", "7200"))
        self.grace_period = int(os.getenv("POD_ERROR_GRACE_PERIOD", "10"))

        if self.get_namespace(self.namespace_str) is None:
            logging.warning(
                "Namespace '%s does not exit. Deleting cronjob.",
                self.namespace_str,
            )
            cronjobs = self.batch_v1.list_namespaced_cron_job("ska-ser-namespace-manager", label_selector=f"manager.cicd.skao.int/managed_namespace={self.namespace_str}")
            logging.info(cronjobs)
            for cronjob in cronjobs.items:
                self.batch_v1.delete_namespaced_cron_job(cronjob.metadata.name, "ska-ser-namespace-manager")

            sys.exit()

        self.logger.info(
            ("Initializing NamespaceCollector for namespace %s" 
            " with TTL: %d and Grace Period: %d"),
            self.namespace_str,
            self.ttl,
            self.grace_period,
        )

    def set_status(self, annotations: Dict[str, str], status: str) -> None:
        """
        Set the status and status timestamp in the annotations.

        :param annotations: The annotations to update.
        :type annotations: Dict[str, str]
        :param status: The status to set.
        :type status: str
        """
        self.logger.debug(
            "Setting status to '%s for namespace: %s",
            status,
            self.namespace_str,
        )
        current_time = datetime.utcnow()
        annotations["cicd.skao.int/status"] = status
        annotations["cicd.skao.int/status_timestamp"] = current_time.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.logger.info(
            "Namespace %s status set to %s", self.namespace_str, status
        )
        self.patch_namespace(self.namespace_str, annotations=annotations)

    def check_stale(
        self, annotations: Dict[str, str], creation_timestamp: datetime
    ) -> None:
        """
        Check if the namespace is stale based on the TTL.

        :param annotations: The annotations to check.
        :type annotations: Dict[str, str]
        """
        self.logger.debug(
            "Checking if namespace '%s is stale", self.namespace_str
        )

        creation_timestamp = creation_timestamp.replace(tzinfo=timezone.utc)
        current_time = datetime.now().replace(tzinfo=timezone.utc)

        self.logger.debug(
            "Creation timestamp for namespace '%s: %s",
            self.namespace_str,
            str(creation_timestamp),
        )

        if creation_timestamp + timedelta(seconds=self.ttl) < current_time:
            self.logger.info("Namespace '%s is stale", self.namespace_str)
            self.set_status(annotations, "stale")
        else:
            self.logger.debug("Namespace '%s is not stale", self.namespace_str)

    def _has_pod_errors(self, pod) -> bool:
        """
        Check if a pod has errors in its container statuses.

        :param pod: The pod to check.
        :type pod: V1Pod
        :return: True if the pod has errors, False otherwise.
        :rtype: bool
        """
        for container_status in pod.status.container_statuses:
            container_name = container_status.name
            state = container_status.state
            if state.waiting and state.waiting.reason in [
                "ImagePullBackOff",
                "ErrImagePull",
            ]:
                self.logger.info(
                    "  Container: %s, Error: %s, Message: %s",
                    container_name,
                    state.waiting.reason,
                    state.waiting.message,
                )
                return True
        return False

    def check_failure(self, annotations: Dict[str, str]) -> None:
        """
        Check for failures in the namespace.

        :param annotations: The annotations to update.
        :type annotations: Dict[str, str]
        """
        self.logger.debug(
            "Checking for failures in namespace: %s", self.namespace_str
        )

        try:
            pods = self.get_pods_from_namespace(self.namespace_str)
        except ApiException as e:
            self.logger.error(
                "Failed to list pods in namespace %s: %s",
                self.namespace_str,
                e,
            )
            return

        has_errors = False
        for pod in pods:
            pod_status = pod.status.phase
            # NOTE: should we check Pending, Failure and Unknown?
            if pod_status == "Pending":
                self.logger.info(
                    "Pod: %s, Status: %s", pod.metadata.name, pod_status
                )
                has_errors = self._has_pod_errors(pod)

        current_time = datetime.utcnow().replace(tzinfo=None)
        status = annotations.get("cicd.skao.int/status", "not_checked")
        status_timestamp = parse(
            annotations.get(
                "cicd.skao.int/status_timestamp",
                current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        ).replace(tzinfo=None)

        grace_time = status_timestamp + timedelta(seconds=self.grace_period)

        if has_errors:
            self.logger.debug(
                "Errors detected in namespace: %s", self.namespace_str
            )

            if status in ["not_checked", "running"]:
                self.set_status(annotations, "failing")

            elif status == "failing" and grace_time < current_time:
                self.set_status(annotations, "failed")

        elif not has_errors and status == "not_checked":
            self.logger.info(
                "No errors detected in namespace: '%s", self.namespace_str
            )
            self.set_status(annotations, "running")

    def check_namespace(self) -> None:
        """
        Check the namespace for staleness and failures.
        """
        self.logger.debug(
            "Starting check for namespace: '%s", self.namespace_str
        )
        namespace = self.get_namespace(self.namespace_str)
        if namespace is None:
            self.logger.error(
                "Failed to get namespace '%s", self.namespace_str
            )
            return

        annotations = namespace.metadata.annotations
        if annotations is None:
            annotations = {}

        if annotations.get("cicd.skao.int/status") is None:
            self.set_status(annotations, "not_checked")

        self.check_stale(annotations, namespace.metadata.creation_timestamp)
        self.check_failure(annotations)
        self.logger.debug(
            "Completed check for namespace: '%s", self.namespace_str
        )
