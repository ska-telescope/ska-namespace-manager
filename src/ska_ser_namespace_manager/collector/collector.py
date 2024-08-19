"""
collector is a generic implementation to abstract the loading of configurations
and the bootstrapping of the kubernetes API
"""

import sys
from typing import Callable, Dict, Optional, TypeVar

import yaml

from ska_ser_namespace_manager.collector.collector_config import (
    CollectorConfig,
)
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
    CollectNamespaceConfig,
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

    namespace: str
    config: T
    namespace_config: CollectNamespaceConfig

    def __init__(
        self, namespace: str, config_class: T, kubeconfig: Optional[str] = None
    ) -> None:
        """
        Initialize NamespaceCollector with the provided information

        :param namespace: The name of the namespace to check
        :param config_class: The class of the configuration
        :param kubeconfig: Kubeconfig to use to access the API
        """
        super().__init__(kubeconfig=kubeconfig)
        self.namespace = namespace
        self.config: T = ConfigLoader().load(config_class)

        namespace_resource = self.get_namespace(self.namespace)
        if namespace_resource is None:
            logging.warning(
                "Namespace '%s no longer exists. Deleting CronJob(s) ...",
                self.namespace,
            )
            sys.exit(1)

        self.namespace_config: CollectNamespaceConfig = match_namespace(
            self.config.namespaces, self.to_dto(namespace_resource)
        )
        if self.namespace_config is None:
            logging.warning(
                "Failed to find collect configuration for namespace '%s',"
                " using a default ..."
            )
            self.namespace_config = CollectNamespaceConfig()

        logging.debug(
            "Configuration: \n%s",
            yaml.safe_dump(
                yaml.safe_load(self.namespace_config.model_dump_json())
            ),
        )

    @classmethod
    def get_actions(cls) -> Dict[CollectActions, Callable]:
        """
        Returns the possible actions for this collector

        :return: Dict of actions for this collector
        """
        return {}
