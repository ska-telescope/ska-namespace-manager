"""
collect_controller provides the collect controller component. This controller
is responsible for creating tasks to collect information on managed
resources
"""

import datetime
import os
import traceback
from typing import Optional

import requests

from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectControllerConfig,
)
from ska_ser_namespace_manager.controller.controller import (
    conditional_controller_task,
    controller_task,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.controller.sharding import (
    NamespaceShardAssigner,
    get_ready_pod_names,
)
from ska_ser_namespace_manager.collector.ownership_collector import (
    OwnershipCollector,
)
from ska_ser_namespace_manager.collector.collector_config import (
    CollectorConfig,
)
from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import match_namespace
from ska_ser_namespace_manager.core.types import (
    NamespaceAnnotations,
    NamespaceStatus,
)
class CollectController(LeaderController):
    """
    CollectController is responsible for creating tasks to collect
    information on managed resources and manage those tasks
    """

    def __init__(self, kubeconfig: Optional[str] = None) -> None:
        """
        Initialize the CollectController
        """
        LeaderController.__init__(
            self,
            CollectControllerConfig,
            [self.check_new_namespaces],
            kubeconfig,
        )

        self.config: CollectControllerConfig
        logging.debug(
            "CollectController initialized for namespace '%s' with %d namespace rules",
            self.config.context.namespace,
            len(self.config.namespaces),
        )
        self.add_tasks(
            [
                self.collect_namespace_health,
                self.collect_namespace_ownership,
            ]
        )

    def get_replica_id(self) -> str:
        """
        Return the current collect-controller replica identity.
        """
        return os.environ.get("HOSTNAME", "")

    def get_active_collect_replicas(self) -> list[str]:
        """
        Return the ready collect-controller replica names for sharding.
        """
        pods = self.get_namespace_pods_by(
            self.config.context.namespace,
            labels=self.config.sharding.pod_labels,
        )
        return get_ready_pod_names(pods)

    def owns_namespace(self, namespace: str) -> bool:
        """
        Return whether this replica owns the namespace shard.
        """
        if not self.config.sharding.enabled:
            return True

        replica_id = self.get_replica_id()
        if replica_id == "":
            return True

        active_replicas = self.get_active_collect_replicas()
        if len(active_replicas) == 0:
            return True

        return NamespaceShardAssigner.owns_namespace(
            namespace,
            replica_id,
            active_replicas,
        )

    @controller_task(period=datetime.timedelta(seconds=1))
    def check_new_namespaces(self) -> None:
        """
        Check for new namespaces and mark them as managed
        """
        unmanaged_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                exclude_annotations={
                    NamespaceAnnotations.MANAGED.value: "true"
                }
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]

        for namespace in unmanaged_namespaces:
            ns_config = match_namespace(
                self.config.namespaces, self.to_dto(namespace)
            )
            if ns_config:
                namespace = namespace.metadata.name
                logging.info(
                    "Managing new namespace '%s'",
                    namespace,
                )
                try:
                    self.patch_namespace(
                        namespace,
                        annotations={
                            NamespaceAnnotations.STATUS: NamespaceStatus.UNKNOWN.value,  # pylint: disable=line-too-long  # noqa: E501
                            NamespaceAnnotations.MANAGED: "true",
                            NamespaceAnnotations.NAMESPACE: namespace,
                        },
                    )
                except (  # pylint: disable=broad-exception-caught
                    Exception
                ) as exc:
                    logging.error(
                        "Error while managing new namespace '%s': %s\n%s",
                        namespace,
                        str(exc),
                        traceback.format_exc(),
                    )

    def _fetch_prometheus_alerts_snapshot(self) -> list | None:
        """
        Fetch the current Prometheus alert snapshot once for the cycle.
        """
        if not self.config.prometheus.enabled:
            return None

        try:
            response = requests.get(
                f"{self.config.prometheus.url}/api/v1/alerts",
                timeout=20,
                verify=(
                    self.config.prometheus.ca_path
                    if self.config.prometheus.ca
                    else not self.config.prometheus.insecure
                ),
            )
            response.raise_for_status()
            return response.json().get("data", {}).get("alerts", [])
        except requests.exceptions.RequestException as exc:
            logging.error("Error fetching alerts from Prometheus: %s", exc)
            return []

    def _get_alerts_by_namespace(self, alerts: list | None) -> dict[str, list]:
        """
        Group Prometheus alerts by namespace.
        """
        if alerts is None:
            return {}

        alerts_by_namespace = {}
        for alert in alerts:
            namespace = alert.get("labels", {}).get("namespace")
            if not namespace:
                continue

            alerts_by_namespace.setdefault(namespace, []).append(alert)

        return alerts_by_namespace

    @controller_task(period=datetime.timedelta(minutes=1))
    def collect_namespace_health(self) -> None:
        """
        Collect namespace health information in-process for the namespaces
        owned by this replica shard.
        """
        managed_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={NamespaceAnnotations.MANAGED.value: "true"}
            )
            if namespace.metadata.name not in self.forbidden_namespaces
            and self.owns_namespace(namespace.metadata.name)
        ]
        alerts_by_namespace = self._get_alerts_by_namespace(
            self._fetch_prometheus_alerts_snapshot()
        )

        for namespace in managed_namespaces:
            try:
                NamespaceCollector(
                    namespace.metadata.name,
                    CollectorConfig,
                ).check_namespace(
                    alerts=alerts_by_namespace.get(namespace.metadata.name)
                )
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error while collecting namespace health for '%s': %s\n%s",
                    namespace.metadata.name,
                    str(exc),
                    traceback.format_exc(),
                )

    @controller_task(period=datetime.timedelta(seconds=10))
    def collect_namespace_ownership(self) -> None:
        """
        Collect ownership information in-process for the namespaces owned by
        this replica shard.
        """
        managed_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={NamespaceAnnotations.MANAGED.value: "true"},
                exclude_annotations={NamespaceAnnotations.OWNER.value: ".+"},
            )
            if namespace.metadata.name not in self.forbidden_namespaces
            and self.owns_namespace(namespace.metadata.name)
        ]

        for namespace in managed_namespaces:
            try:
                OwnershipCollector(
                    namespace.metadata.name,
                    CollectorConfig,
                ).get_owner_info()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Error while collecting owner information for '%s': %s\n%s",
                    namespace.metadata.name,
                    str(exc),
                    traceback.format_exc(),
                )
