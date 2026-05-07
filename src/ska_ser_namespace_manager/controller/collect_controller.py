"""
collect_controller provides the collect controller component. This controller
is responsible for creating tasks to collect information on managed
resources
"""

import datetime
import hashlib
import os
import threading
import traceback
from pathlib import Path
from typing import List, Optional

from kubernetes.client import V1Namespace

from ska_ser_namespace_manager.collector.collector_config import (
    CollectorConfig,
)
from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
    CollectControllerConfig,
    CollectNamespaceConfig,
)
from ska_ser_namespace_manager.controller.controller import (
    conditional_controller_task,
    controller_task,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import match_namespace
from ska_ser_namespace_manager.core.types import (
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.core.utils import parse_timedelta
from ska_ser_namespace_manager.metrics.metrics import MetricsManager


class CollectController(LeaderController):
    """
    CollectController is responsible for creating tasks to collect
    information on managed resources and manage those tasks
    """

    metrics_manager: MetricsManager
    namespace_collector: NamespaceCollector
    namespace_check_threads: dict[str, str]
    NAMESPACE_MANAGER_INSTANCE: str = "ska-ser-namespace-manager"
    NAMESPACE_MANAGER_COMPONENTS: tuple[str, str, str] = (
        "api",
        "collect-controller",
        "action-controller",
    )

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
        self.current_pod_name = os.environ.get(
            "HOSTNAME", os.environ.get("POD_NAME", f"local-{os.getpid()}")
        )
        self.metrics_manager = MetricsManager(
            self.config.metrics, owner=self.current_pod_name
        )
        self.namespace_collector = NamespaceCollector(
            CollectorConfig, kubeconfig
        )
        self.add_tasks(
            [
                self.check_assigned_namespaces,
                self.generate_metrics,
                self.reconcile_metrics_files,
            ]
        )

        self.namespace_check_threads = {}

    def _update_heartbeat(self) -> None:
        """
        Update the local heartbeat file used by the liveness probe.
        """
        heartbeat_path = Path(self.config.heartbeat.path)
        try:
            heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
            heartbeat_path.touch()
        except OSError as exc:
            logging.error(
                "Failed to update collect-controller heartbeat at '%s': %s",
                heartbeat_path,
                exc,
            )

    def cleanup(self, terminate: bool = True) -> None:
        """
        Cleanup collect-controller resources.
        """
        super().cleanup(terminate=terminate)
        self.namespace_collector.gitlab_pipeline_client.close()

    def _get_collect_controller_stateful_set_pods(self) -> Optional[list[str]]:
        """
        Get expected collect-controller pod names from the StatefulSet.
        """
        stateful_set_name = getattr(
            self.config.context, "stateful_set_name", None
        )
        if not isinstance(stateful_set_name, str) or not stateful_set_name:
            return None

        stateful_set = self.get_namespaced_stateful_set(
            namespace=self.config.context.namespace,
            name=stateful_set_name,
        )
        if stateful_set is None:
            logging.warning(
                "Falling back to live collect-controller pod discovery: "
                "StatefulSet '%s' is unavailable in namespace '%s'",
                stateful_set_name,
                self.config.context.namespace,
            )
            return None

        replicas = getattr(getattr(stateful_set, "spec", None), "replicas", 1)
        if replicas is None:
            replicas = 1

        return [f"{stateful_set_name}-{index}" for index in range(replicas)]

    def _get_collect_controller_pods(self) -> list[str]:
        """
        Get collect-controller pod names used for namespace sharding.
        """

        stateful_set_pods = self._get_collect_controller_stateful_set_pods()
        if stateful_set_pods is not None:
            return stateful_set_pods

        pods = self.get_namespace_pods_by(
            namespace=self.config.context.namespace,
            labels={"app.kubernetes.io/component": "collect-controller"},
        )
        pod_names = sorted(
            {
                pod.metadata.name
                for pod in pods
                if pod.metadata
                and pod.metadata.name
                and pod.metadata.deletion_timestamp is None
                and getattr(pod.spec, "service_account_name", None)
                == self.config.context.service_account
            }
        )
        if not pod_names:
            logging.warning(
                "Failed to discover active collect-controller pods in '%s'",
                self.config.context.namespace,
            )

        return pod_names

    def _get_assigned_managed_namespaces(
        self, managed_namespaces: List[V1Namespace]
    ) -> List[V1Namespace]:
        """
        Get the managed namespaces assigned to the current replica.
        """
        pod_names = self._get_collect_controller_pods()
        if not pod_names:
            logging.warning(
                "Skipping namespace checks because no collect-controller "
                "replicas were discovered"
            )
            return []

        if not self.current_pod_name:
            logging.warning(
                "Skipping namespace checks because current pod name is "
                "unavailable"
            )
            return []

        if self.current_pod_name not in pod_names:
            logging.warning(
                "Skipping namespace checks because current pod '%s' was not "
                "found in the discovered replica set %s",
                self.current_pod_name,
                pod_names,
            )
            return []

        assigned_namespaces = []
        for namespace in sorted(
            managed_namespaces, key=lambda item: item.metadata.name
        ):
            hash_index = int(
                hashlib.sha256(
                    namespace.metadata.name.encode("utf-8")
                ).hexdigest(),
                16,
            ) % len(pod_names)
            if pod_names[hash_index] == self.current_pod_name:
                assigned_namespaces.append(namespace)

        return assigned_namespaces

    def _get_namespace_check_period(
        self, config: CollectNamespaceConfig
    ) -> datetime.timedelta:
        """
        Get the interval used for in-process namespace checks.
        """
        schedule = (
            config.actions.get(CollectActions.CHECK_NAMESPACE).schedule
            if config.actions
            else None
        )
        if not schedule:
            return datetime.timedelta(seconds=60)

        try:
            period = parse_timedelta(schedule)
        except (TypeError, ValueError) as exc:
            logging.warning(
                "Invalid check schedule '%s'. Falling back to 60s: %s",
                schedule,
                exc,
            )
            return datetime.timedelta(seconds=60)

        if period.total_seconds() <= 0:
            logging.warning(
                "Non-positive check schedule '%s'. Falling back to 60s",
                schedule,
            )
            return datetime.timedelta(seconds=60)

        return period

    def _get_namespace_thread_name(self, namespace: str) -> str:
        """
        Build a stable thread name for a namespace check.
        """
        return f"namespace-check-{namespace}"

    def is_metrics_enabled(self) -> bool:
        """
        Check if metrics are enabled
        """
        return self.config.metrics.enabled

    def run_namespace_check(
        self, namespace: str, namespace_resource: V1Namespace = None
    ) -> None:
        """
        Run the namespace health collector in-process for a namespace.
        """
        self.namespace_collector.run_action(
            CollectActions.CHECK_NAMESPACE, namespace, namespace_resource
        )

    def run_namespace_check_thread(
        self,
        stop_event: threading.Event,
        namespace: str,
        period: datetime.timedelta,
    ) -> None:
        """
        Run a periodic namespace check thread for a namespace.
        """
        logging.info(
            "Starting namespace check thread '%s' for namespace '%s' with "
            "period '%ss'",
            threading.current_thread().name,
            namespace,
            period.total_seconds(),
        )
        while not self.shutdown_event.is_set() and not stop_event.is_set():
            namespace_resource = self.get_namespace(namespace)
            if namespace_resource is None:
                logging.info(
                    "Stopping namespace thread for '%s' because the "
                    "namespace no longer exists",
                    namespace,
                )
                break

            logging.info(
                "Running namespace check thread '%s' for namespace '%s'",
                threading.current_thread().name,
                namespace,
            )
            try:
                self.run_namespace_check(namespace, namespace_resource)
                self.metrics_manager.record_namespace_check_result("success")
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Namespace check thread failed for namespace '%s': %s\n%s",
                    namespace,
                    exc,
                    traceback.format_exc(),
                )
                self.metrics_manager.record_namespace_check_result("failure")

            if self.wait_for_task_stop(stop_event, period.total_seconds()):
                break

    def create_namespace_check_thread(
        self, namespace: str, period: datetime.timedelta
    ) -> None:
        """
        Create a periodic namespace check thread for a namespace.
        """
        thread_name = self._get_namespace_thread_name(namespace)
        if self.has_task(thread_name):
            return

        self.add_managed_task(
            thread_name, self.run_namespace_check_thread, (namespace, period)
        )
        self.namespace_check_threads[namespace] = thread_name
        logging.info("Created namespace thread for '%s'", namespace)

    def remove_namespace_check_thread(self, namespace: str) -> None:
        """
        Stop and remove a namespace check thread if it exists.
        """
        thread_name = self.namespace_check_threads.pop(namespace, None)
        if thread_name is None:
            thread_name = self._get_namespace_thread_name(namespace)
            if not self.has_task(thread_name):
                return

        self.remove_task(thread_name)
        logging.info("Removed namespace thread for '%s'", namespace)

    @conditional_controller_task(
        period=datetime.timedelta(seconds=1),
        run_if=LeaderController.is_leader,
    )
    def check_new_namespaces(self) -> None:
        """
        Check for new namespaces to manage.
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
                except (
                    Exception  # pylint: disable=broad-exception-caught
                ) as exc:
                    logging.error(
                        "Error while managing new namespace '%s': %s\n%s",
                        namespace,
                        str(exc),
                        traceback.format_exc(),
                    )

    @controller_task(period=datetime.timedelta(seconds=5))
    def check_assigned_namespaces(self) -> None:
        """
        Reconcile periodic namespace check threads for this replica.
        """
        self._update_heartbeat()
        managed_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={NamespaceAnnotations.MANAGED.value: "true"}
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]
        assigned_namespaces = self._get_assigned_managed_namespaces(
            managed_namespaces
        )
        active_namespaces = set()

        for namespace in assigned_namespaces:
            namespace_name = namespace.metadata.name
            namespace_config = match_namespace(
                self.config.namespaces, self.to_dto(namespace)
            )
            if namespace_config is None:
                logging.warning(
                    "Skipping namespace '%s' because it no longer matches "
                    "collector configuration",
                    namespace_name,
                )
                continue
            active_namespaces.add(namespace_name)
            self.create_namespace_check_thread(
                namespace_name,
                self._get_namespace_check_period(namespace_config),
            )

        for namespace in list(self.namespace_check_threads):
            if namespace not in active_namespaces:
                self.remove_namespace_check_thread(namespace)

    @conditional_controller_task(
        period=datetime.timedelta(seconds=5),
        run_if=lambda instance: instance.is_metrics_enabled(),
    )
    def generate_metrics(self) -> None:
        """
        Generate metrics for the namespaces assigned to this replica.
        """
        managed_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={NamespaceAnnotations.MANAGED.value: "true"}
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]
        assigned_namespaces = self._get_assigned_managed_namespaces(
            managed_namespaces
        )
        self.metrics_manager.delete_stale_metrics(
            [ns.metadata.name for ns in assigned_namespaces]
        )

        for ns in assigned_namespaces:
            self.metrics_manager.update_namespace_metrics(ns)

        self.metrics_manager.save_metrics()

    @conditional_controller_task(
        period=datetime.timedelta(seconds=60),
        run_if=LeaderController.is_leader,
    )
    def reconcile_metrics_files(self) -> None:
        """
        Get active namespace-manager pod names with shared metrics files.
        Delete metrics files that do not match active namespace-manager pods.
        """

        pods = self.get_namespace_pods_by(
            namespace=self.config.context.namespace,
            labels={
                "app.kubernetes.io/instance": (self.NAMESPACE_MANAGER_INSTANCE)
            },
        )
        pod_names = sorted(
            {
                pod.metadata.name
                for pod in pods
                if pod.metadata.deletion_timestamp is None
                and (pod.metadata.labels or {}).get(
                    "app.kubernetes.io/component"
                )
                in self.NAMESPACE_MANAGER_COMPONENTS
            }
        )
        if not pod_names:
            logging.warning(
                "Skipping metrics file reconciliation because no active "
                "namespace-manager pods were discovered"
            )
            return

        self.metrics_manager.delete_stale_metrics_files(pod_names)
