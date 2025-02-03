"""
namespace_collector checks Kubernetes namespaces
for staleness and failures
"""

import traceback
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import pytz
import requests
from dateutil.parser import parse
from humanfriendly import format_timespan
from kubernetes.client import V1Namespace

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.types import (
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.core.utils import format_utc, utc


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

    def set_status(
        self,
        namespace: V1Namespace,
        status: str,
        status_annotations: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Set the status and status timestamp in the annotations.

        :param status_annotations: Extra annotations to set on status change
        :param status: The status to set
        """
        annotations = status_annotations or {}
        old_status = (namespace.metadata.annotations or {}).get(
            NamespaceAnnotations.STATUS.value
        )
        if old_status == status:
            logging.info(
                "Namespace '%s' status is already set to: %s",
                self.namespace,
                status,
            )
            return

        annotations[NamespaceAnnotations.STATUS.value] = status
        annotations[NamespaceAnnotations.STATUS_TS.value] = utc()
        annotations[NamespaceAnnotations.NOTIFIED_TS.value] = None
        annotations[NamespaceAnnotations.NOTIFIED_STATUS.value] = None
        logging.info(
            "Setting namespace '%s' status: %s",
            self.namespace,
            status,
        )
        self.patch_namespace(self.namespace, annotations=annotations)

    def check_namespace(self) -> None:
        """
        Check the namespace for staleness and failures throught Prometheus
        alerts or fallback to kubernetes API.
        """
        logging.info("Starting check for namespace '%s'", self.namespace)
        namespace = self.get_namespace(self.namespace)
        if namespace is None:
            logging.error("Failed to get namespace '%s'", self.namespace)
            return

        alerts = []
        if self.prometheus_config.enabled:
            alerts = self.fetch_prometheus_alerts()

        running = self.evaluate_namespace_health(namespace, alerts)

        if running:
            self.set_status(namespace, NamespaceStatus.OK.value)

        logging.debug("Completed check for namespace: '%s", self.namespace)

    def fetch_prometheus_alerts(self) -> list:
        """
        Fetch alerts from Prometheus.

        Returns:
            list: List of matching alerts from Prometheus.
        """
        try:
            url = f"{self.prometheus_config.url}/api/v1/alerts"

            verify = (
                self.prometheus_config.ca_path
                if self.prometheus_config.ca
                else not self.prometheus_config.insecure
            )

            response = requests.get(url, timeout=15, verify=verify)
            response.raise_for_status()

            alerts = response.json().get("data", {}).get("alerts", [])
            return alerts

        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching alerts from Prometheus: {e}")
            return []

    def evaluate_namespace_health(
        self, namespace: V1Namespace, alerts
    ) -> bool:
        """
        Evaluate namespace health based on Prometheus alerts or
        Kubernetes API fallback.

        Returns:
            bool: True if the namespace is healthy, False if there are issues.
        """
        # Check for staleness or failure
        if not alerts:
            return not (
                self.check_stale(namespace) or self.check_failure(namespace)
            )

        # If alerts exist, evaluate based on alerts
        matching_alerts = [
            alert
            for alert in alerts
            if alert["labels"].get("namespace") == self.namespace
        ]
        return not (
            self.check_stale(namespace)
            or self.check_failure(namespace, matching_alerts)
        )

    def check_stale(self, namespace: V1Namespace) -> bool:
        """
        Check if the namespace is stale based on the TTL

        :param namespace: Namespace to check
        :return: True if namespace was stale, False otherwise
        """
        if self.namespace_config.ttl is None:
            return False

        creation_timestamp = namespace.metadata.creation_timestamp.replace(
            tzinfo=timezone.utc
        )
        is_stale = (
            datetime.now(pytz.UTC) - creation_timestamp
            >= self.namespace_config.ttl
        )
        ttl_timeframe = format_timespan(self.namespace_config.ttl)
        if is_stale:
            self.set_status(
                namespace,
                NamespaceStatus.STALE.value,
                {
                    NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(
                        creation_timestamp + self.namespace_config.ttl
                    ),
                    NamespaceAnnotations.STATUS_TIMEFRAME.value: ttl_timeframe,
                },
            )

        return is_stale

    def check_failure(
        self, namespace: V1Namespace, alerts: Optional[list] = None
    ) -> bool:
        """
        Check for failures in the namespace using the alerts from Prometheus,
        with Kubernetes API as a fallback for checking Deployment, StatefulSet,
        or ReplicaSet

        :param namespace: Namespace to check
        :param alerts: List of alerts from Prometheus (default is None)
        :return: True if there are failures, False otherwise.
        """
        annotations = namespace.metadata.annotations or {}
        new_annotations = {}

        if alerts is None:
            failing_resources = self.get_k8s_failing_resources()
            new_annotations[NamespaceAnnotations.FAILING_RESOURCES.value] = (
                ",".join(failing_resources)
            )
        else:
            failing_resources = set()
            for alert in alerts:
                alert_identifier = alert["labels"].get("alertname")
                if alert_identifier:
                    resource_str = self.process_alert_resource(
                        alert, alert_identifier
                    )
                    failing_resources.add(resource_str)
                    new_annotations[
                        NamespaceAnnotations.FAILING_RESOURCES.value
                        + "_"
                        + alert_identifier
                    ] = resource_str

        self.update_common_annotations(new_annotations, annotations)

        return self.update_namespace_status(
            namespace, annotations, failing_resources, new_annotations
        )

    def get_k8s_failing_resources(self) -> set:
        """Helper to get failing resources from Kubernetes API."""
        resource_types = ["deployment", "statefulset", "replicaset"]
        return set(
            resource
            for resource_type in resource_types
            for resource in self._check_resource_status(
                self.namespace, resource_type
            )
        )

    def process_alert_resource(
        self, alert: dict, alert_identifier: str
    ) -> str:
        """Helper method to process individual alert resources."""
        resources = self.extract_resources(alert)
        resource_str = ", ".join(
            [f"{label}={value}" for label, value in resources.items()]
        )
        logging.warning(
            "Alert '%s', in resource: '%s' is firing in namespace '%s'",
            alert_identifier,
            resource_str,
            self.namespace,
        )
        return resource_str

    def extract_resources(self, alert: dict) -> dict:
        """Helper to extract resources from the alert."""
        return {
            label: alert["labels"].get(label)
            for label in [
                "pod",
                "deployment",
                "statefulset",
                "job_name",
                "daemonset",
                "container",
                "persistentvolumeclaim",
            ]
            if alert["labels"].get(label)
        }

    def update_common_annotations(
        self, new_annotations: dict, annotations: dict
    ) -> None:
        """Helper to update common annotation fields."""
        status_timestamp = parse(
            annotations.get(NamespaceAnnotations.STATUS_TS.value, utc())
        ).replace(tzinfo=pytz.UTC)
        new_annotations.update(
            {
                NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(
                    status_timestamp + self.namespace_config.grace_period
                ),
                NamespaceAnnotations.STATUS_TIMEFRAME.value: format_timespan(
                    self.namespace_config.grace_period
                ),
            }
        )

    def update_namespace_status(
        self,
        namespace: V1Namespace,
        annotations: dict,
        failing_resources: set,
        new_annotations: dict,
    ) -> bool:
        """
        Helper to update the namespace status based on the alerts
        or resource checks.
        """
        current_status = annotations.get(NamespaceAnnotations.STATUS.value)

        if not failing_resources:
            return False

        if current_status in [
            NamespaceStatus.OK.value,
            NamespaceStatus.UNKNOWN.value,
        ]:
            self.set_status(
                namespace, NamespaceStatus.UNSTABLE.value, new_annotations
            )

        elif (
            current_status == NamespaceStatus.UNSTABLE.value
            and self._is_after_period("settling_period", annotations)
        ):
            self.set_status(
                namespace, NamespaceStatus.FAILING.value, new_annotations
            )

        elif (
            current_status == NamespaceStatus.FAILING.value
            and self._is_after_period("grace_period", annotations)
        ):
            self.set_status(
                namespace, NamespaceStatus.FAILED.value, new_annotations
            )

        return True

    def _is_after_period(
        self, period_type: str, annotations: Dict[str, str]
    ) -> bool:
        status_timestamp = parse(
            annotations.get(NamespaceAnnotations.STATUS_TS.value, utc())
        ).replace(tzinfo=None)

        try:
            period = getattr(self.namespace_config, period_type)
        except AttributeError as e:
            logging.error(
                "Namespace configuration has no %s attribute.", period_type
            )
            raise AttributeError from e

        time_instant = status_timestamp + period
        logging.debug(
            "Status Timestamp: %s; %s Timestamp: %s",
            status_timestamp,
            period_type,
            time_instant,
        )
        return datetime.now() > time_instant

    def _check_resource_status(
        self, namespace: str, resource_type: str
    ) -> List[str]:
        """
        Check if any resources of the given type in the specified namespace
        have errors.

        :param namespace: The namespace to check.
        :param resource_type: The type of resource to check
        ('deployment', 'statefulset', 'replicaset').
        :return: List of names of failing resources.
        """
        failing_resources = []

        try:
            if resource_type == "deployment":
                res = self.apps_v1.list_namespaced_deployment(
                    namespace, _request_timeout=10
                )
            elif resource_type == "statefulset":
                res = self.apps_v1.list_namespaced_stateful_set(
                    namespace, _request_timeout=10
                )
            elif resource_type == "replicaset":
                res = self.apps_v1.list_namespaced_replica_set(
                    namespace, _request_timeout=10
                )
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
