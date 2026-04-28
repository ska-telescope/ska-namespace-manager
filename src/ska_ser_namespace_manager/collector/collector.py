"""
collector is a generic implementation to abstract the loading of
configurations and the bootstrapping of the kubernetes API
"""

from typing import Callable, Dict, Optional, TypeVar

import yaml
from kubernetes.client import V1Namespace

from ska_ser_namespace_manager.collector.collector_config import (
    CollectorConfig,
)
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
    CollectNamespaceConfig,
    PrometheusConfig,
)
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.kubernetes_api import KubernetesAPI
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import match_namespace

T = TypeVar("T", bound=CollectorConfig)


class Collector(KubernetesAPI):
    """
    A class to check Kubernetes namespaces for staleness and failures.

    This class periodically checks if the namespace are stale based on a
    configured TTL and also checks for pod, deployment, jobs and statefulset
    failures. The results are updated as namespace annotations.
    """

    config: T
    prometheus_config: PrometheusConfig

    def __init__(
        self, config_class: T, kubeconfig: Optional[str] = None
    ) -> None:
        """
        Initialize NamespaceCollector with the provided information

        :param config_class: The class of the configuration
        :param kubeconfig: Kubeconfig to use to access the API
        """
        super().__init__(kubeconfig=kubeconfig)
        self.config: T = ConfigLoader().load(config_class)

        self.prometheus_config = self.config.prometheus

    def get_namespace_config(
        self, namespace_resource: V1Namespace
    ) -> CollectNamespaceConfig:
        """
        Resolve the collector configuration for a namespace at runtime.

        :param namespace_resource: Current namespace object
        :return: Matched namespace config or a default config
        """
        namespace = self.to_dto(namespace_resource)
        namespace_config: CollectNamespaceConfig = match_namespace(
            self.config.namespaces, namespace
        )
        if namespace_config is None:
            logging.warning(
                "Failed to find collect configuration for namespace '%s',"
                " using a default ...",
                namespace.name,
            )
            namespace_config = CollectNamespaceConfig()

        logging.debug(
            "Configuration for namespace '%s':\n%s",
            namespace.name,
            yaml.safe_dump(yaml.safe_load(namespace_config.model_dump_json())),
        )

        return namespace_config

    @classmethod
    def get_actions(cls) -> Dict[CollectActions, Callable]:
        """
        Returns the possible actions for this collector

        :return: Dict of actions for this collector
        """
        return {}

    def run_action(
        self,
        action: CollectActions,
        namespace: str,
    ) -> None:
        """
        Execute a supported action on this collector instance.

        :param action: Action to execute
        :param namespace: Namespace to process
        """
        namespace_resource = self.get_namespace(namespace)
        if namespace_resource is None:
            logging.warning(
                "Namespace '%s' no longer exists. Skipping collection.",
                namespace,
            )
            return

        actions = self.get_actions()
        if action not in actions:
            raise ValueError(
                f"Collector '{type(self).__name__}' does not support "
                f"'{action}'"
            )

        actions[action](self, namespace, namespace_resource)
