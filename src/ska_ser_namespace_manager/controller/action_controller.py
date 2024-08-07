"""
action_controller provides the action controller component. This controller
is responsible for creating tasks to perform actions on managed
resources
"""

import datetime
from typing import Optional

import yaml
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
from ska_ser_namespace_manager.core.utils import utc


class ActionController(Notifier, LeaderController):
    """
    ActionController is responsible for creating tasks to perform actions
    on managed resources and manage those tasks
    """

    slack_client: App

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
                self.notify_failing_unstable_namespaces,
            ],
            kubeconfig,
        )
        self.config: ActionControllerConfig
        Notifier.__init__(self, self.config.notifier.token)

        logging.debug(
            "Configuration: \n%s",
            yaml.safe_dump(yaml.safe_load(self.config.model_dump_json())),
        )

    def delete_namespaces_with_status(self, status: str):
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
            ns_config = match_namespace(
                self.config.namespaces, self.to_dto(namespace)
            )
            if ns_config is None:
                continue

            phase_config: ActionNamespacePhaseConfig = getattr(
                ns_config, status
            )
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

            logging.info(
                "Deleting %s namespace '%s'",
                status,
                namespace.metadata.name,
            )
            self.delete_namespace(
                namespace.metadata.name,
            )

            annotations = namespace.metadata.annotations or {}
            if phase_config.notify_on_delete:
                self.notify_user(
                    address=annotations.get(
                        NamespaceAnnotations.OWNER.value, ""
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

    @controller_task(period=datetime.timedelta(seconds=1))
    def delete_stale_namespaces(self) -> None:
        """
        Looks for namespaces with stale status and deletes them
        :return:
        """
        self.delete_namespaces_with_status(NamespaceStatus.STALE.value)

    @controller_task(period=datetime.timedelta(seconds=1))
    def delete_failed_namespaces(self) -> None:
        """
        Looks for namespaces with failed status and deletes them
        :return:
        """
        self.delete_namespaces_with_status(NamespaceStatus.FAILED.value)

    @controller_task(period=datetime.timedelta(seconds=1))
    def notify_failing_unstable_namespaces(self) -> None:
        """
        Looks for namespaces with failing or unstable status and notifies their
        owners
        :return:
        """
        namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={
                    NamespaceAnnotations.MANAGED.value: "true",
                    NamespaceAnnotations.STATUS.value: "(failing|unstable)",
                    NamespaceAnnotations.OWNER.value: ".+",
                },
                exclude_annotations={
                    NamespaceAnnotations.NOTIFIED_TS.value: ".+"
                },
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]

        for namespace in namespaces:
            annotations = namespace.metadata.annotations or {}
            ns_config = match_namespace(
                self.config.namespaces, self.to_dto(namespace)
            )
            if ns_config is None:
                continue

            status = annotations.get(NamespaceAnnotations.STATUS.value)
            phase_config: ActionNamespacePhaseConfig = getattr(
                ns_config, status
            )
            if not phase_config.notify_on_status:
                continue

            if self.notify_user(
                address=annotations.get(NamespaceAnnotations.OWNER.value, ""),
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
            ):
                annotations[NamespaceAnnotations.NOTIFIED_TS.value] = utc()
                annotations[NamespaceAnnotations.NOTIFIED_STATUS.value] = (
                    status
                )
                self.patch_namespace(
                    namespace.metadata.name, annotations=annotations
                )
