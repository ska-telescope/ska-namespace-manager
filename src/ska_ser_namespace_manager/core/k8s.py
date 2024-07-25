"""
This module provides a Kubernetes utility class to interact with a Kubernetes
cluster.

The K8s class offers methods for loading Kubernetes configurations,
fetching namespaces and pods, and patching namespace annotations.

Classes:
    K8s: A singleton class to provide abstraction from Kubernetes configuration
    loading and operations.

Functions:
    None

Usage:
    To use this module, create an instance of the K8s class and call
    the desired method.
    Example:
        k8s = K8s()
        k8s.load_kubeconfig()
"""

from typing import Dict, List, Optional

from kubernetes import client, config

from ska_ser_namespace_manager.core.logging import logging


class KubernetesAPI:
    """
    K8s is a singleton class to provide abstraction from Kubernetes
    configuration loading and operations.
    """

    def __init__(self, kubeconfig_path: Optional[str] = None) -> None:
        """
        Initializes base config properties.

        :return: None
        """
        self.load_kubeconfig(kubeconfig_path)
        self.v1 = client.CoreV1Api()
        self.batch_v1 = client.BatchV1Api()

    def load_kubeconfig(self, kubeconfig_path: Optional[str] = None) -> None:
        """
        Load Kubernetes configuration.

        :param kubeconfig_path: Optional path to kubeconfig file
        :type kubeconfig_path: Optional[str]
        :return: None
        """
        try:
            if kubeconfig_path is not None:
                config.load_kube_config(config_file=kubeconfig_path)
                logging.info("Loaded kubeconfig from %s", kubeconfig_path)
            else:
                config.load_incluster_config()
                logging.info("Loaded in-cluster kubeconfig")
        except Exception as e:
            logging.error("Failed to load kubeconfig: %s", e)
            raise

    def get_pods_from_namespace(
        self, namespace: str
    ) -> Optional[List[client.V1Pod]]:
        """
        Get the list of pods for a namespace.

        :param namespace: The name of the namespace
        :type namespace: str
        :return: List of pods
        :rtype: Optional[List[client.V1Pod]]
        """
        try:
            pods = self.v1.list_namespaced_pod(namespace)
            return pods.items
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list pods: %s", e)
            return []

    def get_all_namespaces(self) -> List[str]:
        """
        Get the list of namespaces.

        :return: List of namespace names
        :rtype: List[str]
        """
        try:
            namespaces = self.v1.list_namespace().items
            return [ns.metadata.name for ns in namespaces]
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list namespaces: %s", e)
            return []

    def get_namespace(self, namespace: str) -> Optional[client.V1Namespace]:
        """
        Fetch the namespace details.

        :param namespace: The name of the namespace
        :type namespace: str
        :return: The namespace object if found, else None
        :rtype: Optional[client.V1Namespace]
        """
        logging.debug("Fetching namespace: %s", namespace)
        try:
            ns = self.v1.read_namespace(name=namespace)
            logging.debug("Namespace %s fetched successfully", namespace)
            return ns
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to read namespace %s: %s", namespace, e)
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
        :type labels: Optional[Dict[str, str]]
        :param annotations: Optional dictionary of annotations to filter
        namespaces
        :type annotations: Optional[Dict[str, str]]
        :param exclude_labels: Optional dictionary of labels to exclude
        namespaces
        :type exclude_labels: Optional[Dict[str, str]]
        :param exclude_annotations: Optional dictionary of annotations to
        exclude namespaces
        :type exclude_annotations: Optional[Dict[str, str]]
        :return: List of namespaces matching the criteria
        :rtype: List[client.V1Namespace]
        """
        try:
            namespaces = self.v1.list_namespace().items
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

        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to list namespaces: %s", e)
            return []

    def patch_namespace(
        self,
        namespace: str,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Patch the namespace with the provided labels and/or annotations.

        :param namespace: The name of the namespace
        :type namespace: str
        :param labels: Optional dictionary of labels to patch the namespace
        with
        :type labels: Optional[Dict[str, str]]
        :param annotations: Optional dictionary of annotations to patch the
        namespace with
        :type annotations: Optional[Dict[str, str]]
        :return: None
        """
        logging.debug("Patching namespace: %s", namespace)
        body = {"metadata": {}}
        if labels:
            body["metadata"]["labels"] = labels
        if annotations:
            body["metadata"]["annotations"] = annotations

        try:
            self.v1.patch_namespace(name=namespace, body=body)
            logging.debug("Namespace %s patched successfully", namespace)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to patch namespace %s: %s", namespace, e)
            raise

    def delete_namespace(self, namespace: str) -> None:
        """
        Delete a namespace.

        :param namespace: The name of the namespace to delete
        :type namespace: str
        :return: None
        """
        logging.debug("Deleting namespace: %s", namespace)
        try:
            self.v1.delete_namespace(name=namespace)
            logging.debug("Namespace %s deleted successfully", namespace)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error("Failed to delete namespace %s: %s", namespace, e)
            raise
