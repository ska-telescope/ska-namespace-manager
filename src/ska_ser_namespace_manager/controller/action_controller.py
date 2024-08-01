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
                    phase_config.delete_grace_period.total_seconds(),
                )

                if phase_config.notify_on_delete:
                    logging.info("Notified owner of namespace deletion")
                    # TODO: Actually notify owner

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
