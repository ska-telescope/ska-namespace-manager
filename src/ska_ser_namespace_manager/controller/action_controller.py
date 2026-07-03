"""
action_controller provides the action controller component. This controller
is responsible for creating tasks to perform actions on managed
resources
"""

import datetime
import json
import os
from typing import Optional

from slack_bolt import App

from ska_ser_namespace_manager.controller.action_controller_config import (
    ActionControllerConfig,
    ActionNamespacePhaseConfig,
)
from ska_ser_namespace_manager.controller.controller import controller_task
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import match_namespace
from ska_ser_namespace_manager.core.notifier import Notifier
from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.core.utils import (
    ALERT_SUGGESTIONS,
    format_labels_resources,
    utc,
)
from ska_ser_namespace_manager.metrics.metrics import MetricsManager


class ActionController(Notifier, LeaderController):
    """
    ActionController is responsible for creating tasks to perform actions
    on managed resources and manage those tasks
    """

    slack_client: App
    metrics_manager: MetricsManager

    def __init__(self, kubeconfig: Optional[str] = None) -> None:
        """
        Initialize the CollectController
        """
        LeaderController.__init__(
            self,
            ActionControllerConfig,
            [
                self.delete_stale_namespaces,
                self.delete_failed_namespaces,
                self.delete_cancelled_namespaces,
                self.delete_superseded_namespaces,
                self.notify_status_namespaces,
            ],
            kubeconfig,
        )
        self.config: ActionControllerConfig
        self.current_pod_name = os.environ.get(
            "HOSTNAME", os.environ.get("POD_NAME", f"local-{os.getpid()}")
        )
        self.metrics_manager = MetricsManager(
            self.config.metrics, owner=self.current_pod_name
        )
        Notifier.__init__(self, self.config.notifier.token)

    def is_metrics_enabled(self) -> bool:
        """
        Check if metrics are enabled.
        """
        return self.config.metrics.enabled

    def _format_labels_resources(self, labels: dict) -> str:
        """
        Formats string based on the labels.
        Returns a string of resources in the format 'label=value'.
        """
        return format_labels_resources(labels)

    def _process_failing_resources(self, resources_json=str) -> dict:
        """
        Processes and combines alert annotations from the given JSON string.

        :param resources_json: JSON string containing the alerts.
        :return: Dictionary of combined alert annotations.
        """
        if not resources_json:
            return {}

        try:
            alerts = json.loads(resources_json)
        except json.JSONDecodeError:
            return {}

        if all(isinstance(item, str) for item in alerts):
            return {}

        processed_alerts = {}
        for alert in alerts:
            alertname = alert["labels"].get("alertname")
            if alertname not in processed_alerts:
                processed_alerts[alertname] = {
                    "failing_resources": [],
                    "runbook_url": None,
                }

            resource_str = self._format_labels_resources(alert["labels"])
            if resource_str:
                processed_alerts[alertname]["failing_resources"].append(resource_str)
            runbook_url = alert["annotations"].get("runbook_url")

            if runbook_url:
                processed_alerts[alertname]["runbook_url"] = runbook_url

        for alert_data in processed_alerts.values():
            alert_data["failing_resources"] = "; ".join(alert_data["failing_resources"])
        return processed_alerts

    def _summarize_failing_resources(self, resources_json: str) -> str:
        """
        Builds a human-readable summary of the failing resources recorded
        in a namespace's annotation, supporting both the Kubernetes API
        format (a list of resource name strings) and the Prometheus alerts
        format (a list of alert dictionaries).

        :param resources_json: JSON string from the failing_resources
            annotation.
        :return: Human-readable summary, or an empty string if there is
            nothing to report.
        """
        if not resources_json:
            return ""

        try:
            resources = json.loads(resources_json)
        except json.JSONDecodeError:
            return resources_json

        if not resources:
            return ""

        if all(isinstance(item, str) for item in resources):
            return ", ".join(resources)

        summaries = []
        for alert in resources:
            alertname = alert.get("labels", {}).get("alertname", "unknown")
            resource_str = self._format_labels_resources(alert.get("labels", {}))
            summaries.append(
                f"{alertname}: {resource_str}" if resource_str else alertname
            )

        return "; ".join(summaries)

    def _delete_namespaces_with_status(self, status: str):
        """
        Deletes namespaces with a particular status

        :param status: Status to search and delete
        """
        namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={
                    NamespaceAnnotations.MANAGED.value: "true",
                    NamespaceAnnotations.STATUS.value: status,
                }
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]

        for namespace in namespaces:
            ns_config = match_namespace(self.config.namespaces, self.to_dto(namespace))
            if ns_config is None:
                continue

            phase_config: ActionNamespacePhaseConfig = getattr(ns_config, status)
            if not phase_config.delete:
                logging.debug(
                    "Namespace '%s' is %s but won't be deleted",
                    namespace.metadata.name,
                    status,
                )
                continue

            if namespace.status.phase == "Terminating":
                logging.debug(
                    "Namespace '%s' is already terminating",
                    namespace.metadata.name,
                )
                continue

            annotations = namespace.metadata.annotations or {}
            failing_resources = self._summarize_failing_resources(
                annotations.get(NamespaceAnnotations.FAILING_RESOURCES.value, "")
            )
            if failing_resources:
                logging.info(
                    "Namespace '%s' had failing resources before deletion: %s",
                    namespace.metadata.name,
                    failing_resources,
                )

            logging.info(
                "Deleting %s namespace '%s'",
                status,
                namespace.metadata.name,
            )
            self.delete_namespace(
                namespace.metadata.name,
            )
            if self.is_metrics_enabled():
                self.metrics_manager.record_namespace_deletion(status)
                self.metrics_manager.save_metrics()

            if phase_config.notify_on_delete:
                self.notify_user(
                    address=annotations.get(
                        CicdAnnotations.NOTIFICATION_ADDRESS.value, ""
                    ),
                    template="namespace-deleted-notification.j2",
                    status=status,
                    target_namespace=namespace.metadata.name,
                    status_timeframe=annotations.get(
                        NamespaceAnnotations.STATUS_TIMEFRAME.value,
                    ),
                    job_url=namespace.metadata.annotations.get(
                        CicdAnnotations.JOB_URL.value
                    ),
                )

    @controller_task(period=datetime.timedelta(seconds=5))
    def delete_stale_namespaces(self) -> None:
        """
        Looks for namespaces with stale status and deletes them
        :return:
        """
        self._delete_namespaces_with_status(NamespaceStatus.STALE.value)

    @controller_task(period=datetime.timedelta(seconds=5))
    def delete_failed_namespaces(self) -> None:
        """
        Looks for namespaces with failed status and deletes them
        :return:
        """
        self._delete_namespaces_with_status(NamespaceStatus.FAILED.value)

    @controller_task(period=datetime.timedelta(seconds=5))
    def delete_cancelled_namespaces(self) -> None:
        """
        Looks for namespaces with cancelled status and deletes them
        :return:
        """
        self._delete_namespaces_with_status(NamespaceStatus.CANCELLED.value)

    @controller_task(period=datetime.timedelta(seconds=5))
    def delete_superseded_namespaces(self) -> None:
        """
        Looks for namespaces with superseded status and deletes them
        :return:
        """
        self._delete_namespaces_with_status(NamespaceStatus.SUPERSEDED.value)

    @controller_task(period=datetime.timedelta(seconds=5))
    def notify_status_namespaces(self) -> None:
        """
        Looks for namespaces with notifiable status and notifies their owners
        :return:
        """
        namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={
                    NamespaceAnnotations.MANAGED.value: "true",
                    NamespaceAnnotations.STATUS.value: (
                        "(failing|unstable|cancelled|superseded)"
                    ),
                    CicdAnnotations.NOTIFICATION_ADDRESS.value: ".+",
                },
                exclude_annotations={NamespaceAnnotations.NOTIFIED_TS.value: ".+"},
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]

        for namespace in namespaces:
            annotations = namespace.metadata.annotations or {}
            ns_config = match_namespace(self.config.namespaces, self.to_dto(namespace))
            if ns_config is None:
                continue

            status = annotations.get(NamespaceAnnotations.STATUS.value)
            failing_resources = annotations.get(
                NamespaceAnnotations.FAILING_RESOURCES.value
            )
            phase_config: ActionNamespacePhaseConfig = getattr(ns_config, status)
            if not phase_config.notify_on_status:
                continue

            if self.notify_user(
                address=annotations.get(CicdAnnotations.NOTIFICATION_ADDRESS.value, ""),
                template=f"{status}-namespace-notification.j2",
                status=status,
                target_namespace=namespace.metadata.name,
                status_timeframe=annotations.get(
                    NamespaceAnnotations.STATUS_TIMEFRAME.value
                ),
                finalize_at=namespace.metadata.annotations.get(
                    NamespaceAnnotations.STATUS_FINALIZE_AT.value
                ),
                job_url=namespace.metadata.annotations.get(
                    CicdAnnotations.JOB_URL.value
                ),
                alerts=self._process_failing_resources(failing_resources),
                alert_suggestions=ALERT_SUGGESTIONS,
            ):
                annotations[NamespaceAnnotations.NOTIFIED_TS.value] = utc()
                annotations[NamespaceAnnotations.NOTIFIED_STATUS.value] = status
                self.patch_namespace(namespace.metadata.name, annotations=annotations)
