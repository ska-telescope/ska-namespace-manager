"""
namespace_collector checks Kubernetes namespaces
for staleness and failures
"""

import json
import traceback
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Tuple

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
        status: NamespaceStatus,
        status_annotations: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Set the status and status timestamp in the annotations.

        :param status_annotations: Extra annotations to set on status change
        :param status: The status to set
        """
        previous_annotations = namespace.metadata.annotations or {}
        annotations = status_annotations or {}
        previous_status = NamespaceStatus.from_string(
            (previous_annotations).get(
                NamespaceAnnotations.STATUS, NamespaceStatus.UNKNOWN.value
            )
        )
        status_timestamp = parse(
            previous_annotations.get(NamespaceAnnotations.STATUS_TS, utc())
        ).replace(tzinfo=pytz.UTC)
        if previous_status != status:
            annotations[NamespaceAnnotations.STATUS.value] = status.value
            annotations[NamespaceAnnotations.STATUS_TS.value] = utc()
            annotations[NamespaceAnnotations.NOTIFIED_TS.value] = None
            annotations[NamespaceAnnotations.NOTIFIED_STATUS.value] = None
            status_timestamp = parse(
                annotations.get(NamespaceAnnotations.STATUS_TS.value, utc())
            ).replace(tzinfo=pytz.UTC)
            logging.info(
                "Setting namespace '%s' status: %s",
                self.namespace,
                status,
            )

        if status == NamespaceStatus.OK and self.namespace_config.ttl:
            annotations.update(
                {
                    NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(  # noqa: E501 pylint: disable=line-too-long
                        status_timestamp + self.namespace_config.ttl
                    ),
                    NamespaceAnnotations.STATUS_TIMEFRAME.value: format_timespan(  # noqa: E501 pylint: disable=line-too-long
                        self.namespace_config.ttl
                    ),
                }
            )

        if status in [NamespaceStatus.UNSTABLE, NamespaceStatus.FAILING]:
            ttl = self.namespace_config.grace_period
            if status == NamespaceStatus.UNSTABLE:
                ttl += self.namespace_config.settling_period

            annotations.update(
                {
                    NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(
                        status_timestamp + ttl
                    ),
                    NamespaceAnnotations.STATUS_TIMEFRAME.value: format_timespan(  # noqa: E501 pylint: disable=line-too-long
                        ttl
                    ),
                }
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

        alerts = None
        if self.prometheus_config.enabled:
            alerts = self.fetch_prometheus_alerts()

        new_status, new_annotations = self.evaluate_namespace_health(
            namespace, alerts
        )
        self.set_status(namespace, new_status, new_annotations)

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
            response = requests.get(url, timeout=20, verify=verify)
            response.raise_for_status()

            return response.json().get("data", {}).get("alerts", [])
        except requests.exceptions.RequestException as e:
            logging.error(f"Error fetching alerts from Prometheus: {e}")
            return []

    def evaluate_namespace_health(
        self, namespace: V1Namespace, alerts: Optional[list] = None
    ) -> Tuple[NamespaceStatus, dict]:
        """
        Evaluate namespace health based on Prometheus alerts or
        Kubernetes API fallback.

        Returns:
            bool: True if the namespace is healthy, False if there are issues.
        """
        matching_alerts = alerts
        if alerts:
            matching_alerts = [
                alert
                for alert in alerts
                if alert["labels"].get("namespace") == self.namespace
            ]

        stale, annotations = self.check_stale(namespace)
        if stale:
            return NamespaceStatus.STALE, annotations

        return self.check_failure(namespace, matching_alerts)

    def check_stale(self, namespace: V1Namespace) -> Tuple[bool, dict]:
        """
        Check if the namespace is stale based on the TTL

        :param namespace: Namespace to check
        :return: True if namespace was stale, False otherwise
        """
        if self.namespace_config.ttl is None:
            return False, {}

        creation_timestamp = namespace.metadata.creation_timestamp.replace(
            tzinfo=timezone.utc
        )
        is_stale = (
            datetime.now(pytz.UTC) - creation_timestamp
            >= self.namespace_config.ttl
        )
        ttl_timeframe = format_timespan(self.namespace_config.ttl)
        annotations = {}
        if is_stale:
            annotations = {
                NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(
                    creation_timestamp + self.namespace_config.ttl
                ),
                NamespaceAnnotations.STATUS_TIMEFRAME.value: ttl_timeframe,
            }

        return is_stale, annotations

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

        if alerts is None:
            failing_resources = self.get_k8s_failing_resources()
        else:
            failing_resources = self.process_alerts(alerts)

        new_annotations = {
            NamespaceAnnotations.FAILING_RESOURCES.value: json.dumps(
                failing_resources
            )
        }
        if len(failing_resources) == 0:
            return NamespaceStatus.OK, new_annotations

        return self.transition_namespace_status(annotations), new_annotations

    def get_k8s_failing_resources(self) -> List[str]:
        """Helper to get failing resources from Kubernetes API."""
        resource_types = ["deployment", "statefulset", "replicaset"]
        return list(
            set(
                resource
                for resource_type in resource_types
                for resource in self._check_resource_status(
                    self.namespace, resource_type
                )
            )
        )

    def process_alerts(self, alerts: list) -> List[dict]:
        """Helper method to process alerts."""
        alerts_processed = []
        for alert in alerts:
            alert_identifier = alert["labels"].get("alertname")
            if not alert_identifier:
                logging.warning("Alert missing 'alertname', skipping it.")
                continue

            if self.validate_alert(alert):
                alert_data = {
                    "labels": alert["labels"],
                    "annotations": {
                        "runbook_url": alert["annotations"].get(
                            "runbook_url", ""
                        ),
                    },
                }
                alerts_processed.append(dict(alert_data))

        return alerts_processed

    def validate_alert(self, alert: dict) -> bool:
        """Helper method to process individual alert resources."""

        alert_identifier = alert["labels"].get("alertname")
        if alert_identifier in self.prometheus_config.whitelisted_alerts:
            severity = alert["labels"].get("severity", "unknown")

            if severity != "critical":
                logging.warning(
                    "Alert '%s' is whitelisted with severity '%s', skipping.",
                    alert_identifier,
                    severity,
                )
                return False
        else:
            logging.warning("Alert '%s' is firing.", alert_identifier)
        return True

    def transition_namespace_status(
        self,
        annotations: dict,
    ) -> bool:
        """
        Helper to update the namespace status based on the alerts
        or resource checks.
        """
        current_status = NamespaceStatus.from_string(
            annotations.get(NamespaceAnnotations.STATUS.value)
        )
        if current_status in [
            NamespaceStatus.OK,
            NamespaceStatus.UNKNOWN,
        ]:
            return NamespaceStatus.UNSTABLE

        if (
            current_status == NamespaceStatus.UNSTABLE
            and self._is_after_period("settling_period", annotations)
        ):
            return NamespaceStatus.FAILING

        if (
            current_status == NamespaceStatus.FAILING
            and self._is_after_period("grace_period", annotations)
        ):
            return NamespaceStatus.FAILED

        return current_status

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
