"""
kubernetes_api provides a Kubernetes abstraction class to interact
with a Kubernetes cluster. It offers methods for loading Kubernetes
configurations and core namespace and resource management functionality
"""

import traceback
from typing import Dict, List, Optional

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException

from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import Namespace


class KubernetesAPI:
    """
    KubernetesAPI is a singleton class to provide abstraction from
    Kubernetes configuration loading and basic operations.
    """

    def __init__(self, kubeconfig: Optional[str] = None) -> None:
        """
        Initializes base config properties.

        :return: None
        """
        self.load_kubeconfig(kubeconfig)
        self.v1 = client.CoreV1Api()
        self.apps_v1 = client.AppsV1Api()
        self.batch_v1 = client.BatchV1Api()

    def load_kubeconfig(self, kubeconfig: Optional[str] = None) -> None:
        """
        Load Kubernetes configuration.

        :param kubeconfig: Optional path to kubeconfig file
        :type kubeconfig: Optional[str]
        :return: None
        """
        try:
            if kubeconfig is not None:
                config.load_kube_config(config_file=kubeconfig)
                logging.info("Loaded kubeconfig from %s", kubeconfig)
            else:
                config.load_incluster_config()
                logging.info("Loaded in-cluster kubeconfig")
        except Exception as exc:
            logging.error("Failed to load a valid kubeconfig: %s", exc)
            traceback.print_exception(exc)
            raise

    def get_namespaces(self) -> List[str]:
        """
        Get the list of namespace names

        :return: List of namespace names
        """
        try:
            namespaces = self.v1.list_namespace().items
            return [ns.metadata.name for ns in namespaces]
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list namespaces: %s", exc)
            traceback.print_exception(exc)
            return []

    def get_namespace(self, namespace: str) -> Optional[client.V1Namespace]:
        """
        Gets namespace

        :param namespace: The name of the namespace
        :return: The namespace object if found, else None
        """
        logging.debug("Fetching namespace: %s", namespace)
        try:
            ns = self.v1.read_namespace(name=namespace)
            logging.debug("Namespace %s fetched successfully", namespace)
            return ns
        except ApiException as exc:
            if exc.status != 404:
                logging.error(
                    "Failed to read namespace '%s': %s", namespace, exc
                )
                traceback.print_exception(exc)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to read namespace '%s': %s", namespace, exc)
            traceback.print_exception(exc)

        return None

    def get_namespaces_by(
        self,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        exclude_labels: Optional[Dict[str, str]] = None,
        exclude_annotations: Optional[Dict[str, str]] = None,
    ) -> List[client.V1Namespace]:
        """
        List all namespaces with a given label, annotation, or combination of
        both, and optionally exclude namespaces with certain labels or
        annotations.

        :param labels: Optional dictionary of labels to filter namespaces
        :param annotations: Optional dictionary of annotations to filter
        namespaces
        :param exclude_labels: Optional dictionary of labels to exclude
        namespaces
        :param exclude_annotations: Optional dictionary of annotations to
        exclude namespaces
        :return: List of namespaces matching the criteria
        """
        try:
            namespaces: List[client.V1Namespace] = (
                self.v1.list_namespace().items
            )
            filtered_namespaces = []
            for ns in namespaces:
                ns_labels = ns.metadata.labels or {}
                ns_annotations = ns.metadata.annotations or {}

                if labels and not all(
                    ns_labels.get(key) == value
                    for key, value in labels.items()
                ):
                    continue

                if annotations and not all(
                    ns_annotations.get(key) == value
                    for key, value in annotations.items()
                ):
                    continue

                if exclude_labels and any(
                    ns_labels.get(key) == value
                    for key, value in exclude_labels.items()
                ):
                    continue

                if exclude_annotations and any(
                    ns_annotations.get(key) == value
                    for key, value in exclude_annotations.items()
                ):
                    continue

                filtered_namespaces.append(ns)

            return filtered_namespaces
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list namespaces: %s", exc)
            traceback.print_exception(exc)
            return []

    def get_namespace_pods(
        self, namespace: str
    ) -> Optional[List[client.V1Pod]]:
        """
        Get the list of pods for a namespace.

        :param namespace: The name of the namespace
        :return: List of pods
        """
        try:
            pods: client.V1PodList = self.v1.list_namespaced_pod(namespace)
            return pods.items
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list pods: %s", exc)
            traceback.print_exception(exc)
            return []

    def patch_namespace(
        self,
        namespace: str,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
    ):
        """
        Patch the namespace with the provided labels and/or annotations.

        :param namespace: The name of the namespace
        :param labels: Optional dictionary of labels to patch the namespace
        with
        :param annotations: Optional dictionary of annotations to patch the
        namespace with
        :return:
        """
        logging.debug(
            "Patching namespace '%s' with labels '%s' and annotations '%s'",
            namespace,
            labels,
            annotations,
        )
        body = {"metadata": {}}
        if labels:
            body["metadata"]["labels"] = labels
        if annotations:
            body["metadata"]["annotations"] = annotations

        try:
            self.v1.patch_namespace(name=namespace, body=body)
            logging.debug("Namespace %s patched successfully", namespace)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to patch namespace '%s': %s", namespace, exc)
            traceback.print_exception(exc)

    def delete_namespace(self, namespace: str, grace_period: int = 0) -> None:
        """
        Delete a namespace.

        :param namespace: The name of the namespace to delete
        :param grace_period: Grace period to delete the namespace
        :return:
        """
        logging.debug("Deleting namespace '%s'", namespace)
        try:
            self.v1.delete_namespace(
                name=namespace, grace_period_seconds=int(grace_period)
            )
            logging.debug("Namespace '%s' deleted successfully", namespace)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Failed to delete namespace '%s': %s", namespace, exc
            )
            traceback.print_exception(exc)

    def get_cronjobs_by(
        self,
        namespace: str,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        exclude_labels: Optional[Dict[str, str]] = None,
        exclude_annotations: Optional[Dict[str, str]] = None,
    ) -> List[client.V1Namespace]:
        """
        List all cronjobs within a namespace given label, annotation, or
        combination of both, and optionally exclude cronjobs with certain
        labels or annotations.

        :param labels: Optional dictionary of labels to filter cronjobs
        :param annotations: Optional dictionary of annotations to filter
        cronjobs
        :param exclude_labels: Optional dictionary of labels to exclude
        cronjobs
        :param exclude_annotations: Optional dictionary of annotations to
        exclude cronjobs
        :return: List of cronjobs matching the criteria
        """
        try:
            cronjobs: List[client.V1CronJob] = (
                self.batch_v1.list_namespaced_cron_job(
                    namespace=namespace
                ).items
            )
            filtered_cronjobs = []
            for cj in cronjobs:
                cj_labels = cj.metadata.labels or {}
                cj_annotations = cj.metadata.annotations or {}

                if labels and not all(
                    cj_labels.get(key) == value
                    for key, value in labels.items()
                ):
                    continue

                if annotations and not all(
                    cj_annotations.get(key) == value
                    for key, value in annotations.items()
                ):
                    continue

                if exclude_labels and any(
                    cj_labels.get(key) == value
                    for key, value in exclude_labels.items()
                ):
                    continue

                if exclude_annotations and any(
                    cj_annotations.get(key) == value
                    for key, value in exclude_annotations.items()
                ):
                    continue

                filtered_cronjobs.append(cj)

            return filtered_cronjobs
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list cronjobs: %s", exc)
            traceback.print_exception(exc)
            return []

    def to_dto(self, resource: client.V1Namespace | None) -> Namespace:
        """
        Converts a native kubernetes resource into a application specific
        data transfer object (DTO)

        :param resource: Kubernetes API resource to convert
        :return: Converted DTO
        """
        if resource is None:
            return None

        metadata: client.V1ObjectMeta = resource.metadata
        return Namespace(
            name=metadata.name,
            labels=metadata.labels,
            annotations=metadata.annotations,
        )
