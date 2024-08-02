"""
action_controller provides the action controller component. This controller
is responsible for creating tasks to perform actions on managed
resources
"""

import datetime
from typing import Optional

import yaml

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
from ska_ser_namespace_manager.core.utils import decode_slack_address, now


class ActionController(LeaderController):
    """
    ActionController is responsible for creating tasks to perform actions
    on managed resources and manage those tasks
    """

    def __init__(self, kubeconfig: Optional[str] = None) -> None:
        """
        Initialize the CollectController
        """
        super().__init__(
            ActionControllerConfig,
            [self.delete_stale_namespaces, self.delete_failed_namespaces],
            kubeconfig,
        )
        self.config: ActionControllerConfig
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
                    "manager.cicd.skao.int/managed": "true",
                    "manager.cicd.skao.int/status": status,
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
            if phase_config.delete:
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
                    self.notify_via_slack(
                        address=annotations.get(
                            "manager.cicd.skao.int/owner", ""
                        ),
                        template="namespace_deleted_notification.j2",
                        namespace=namespace.metadata.name,
                        status=status,
                    )
                    # TODO: Actually notify owner

    def notify_via_slack(self, address: str, template: str, **kwargs) -> bool:
        """
        Notifies a user via slack that some action is to be or was taken

        :param address: Slack address, encoded by encode_slack_address
        :param template: Template to use
        :param kwargs: Arguments to pass to the template
        :return: True if the notification was sent, false otherwise
        """
        user, slack_id = decode_slack_address(address)
        if slack_id is None:
            logging.error("Couldn't find a valid slack id to notify the user")
            return False

        message = self.template_factory.render(template, user=user, **kwargs)
        logging.info(message)

        return True

    @controller_task(period=datetime.timedelta(seconds=1))
    def delete_stale_namespaces(self) -> None:
        """
        Looks for namespaces with stale status and deletes them
        :return:
        """
        self.delete_namespaces_with_status("stale")

    @controller_task(period=datetime.timedelta(seconds=1))
    def delete_failed_namespaces(self) -> None:
        """
        Looks for namespaces with failed status and deletes them
        :return:
        """
        self.delete_namespaces_with_status("failed")

    @controller_task(period=datetime.timedelta(seconds=1))
    def notify_failing_namespaces(self) -> None:
        """
        Looks for namespaces with failing status and notifies their
        owners
        :return:
        """
        namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={
                    "manager.cicd.skao.int/managed": "true",
                    "manager.cicd.skao.int/status": "failing",
                    "manager.cicd.skao.int/owner": ".*",
                },
                exclude_annotations={
                    "manager.cicd.skao.int/notified_failing_timestamp": ".*"
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

            # TODO: Convert into a job
            if self.notify_via_slack(
                address=annotations.get("manager.cicd.skao.int/owner", ""),
                template="failing_namespace_notification.j2",
                namespace=namespace.metadata.name,
                delete_at=namespace.metadata.annotations.get(
                    "manager.cicd.skao.int/delete_at"
                ),
            ):
                annotations[
                    "manager.cicd.skao.int/notified_failing_timestamp"
                ] = now()
                self.patch_namespace(
                    namespace.metadata.name, annotations=annotations
                )
