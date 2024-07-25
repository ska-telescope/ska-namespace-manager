"""
This module provides the action controller component. This controller
is responsible for creating tasks to perform actions on managed
resources

Usage:
    To use this module, create an instance of ActionController and
    call the run() method.
    Example:
        ActionController().run()
"""

import datetime

from ska_ser_namespace_manager.controller.action_controller_config import (
    ActionControllerConfig,
)
from ska_ser_namespace_manager.controller.controller import controller_task
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.logging import logging


class ActionController(LeaderController):
    """
    ActionController is responsible for creating tasks to perform actions
    on managed resources and manage those tasks
    """

    def __init__(self) -> None:
        """
        Initialize the CollectController
        """
        super().__init__(
            ActionControllerConfig,
            [self.delete_stale_namespaces, self.delete_failed_namespaces],
        )

    @controller_task(period=datetime.timedelta(seconds=1))
    def delete_stale_namespaces(self) -> None:
        """
        Looks for namespaces with stale status and deletes them.
        :return:
        """
        stale_namespaces = self.get_namespaces_by(
            annotations={
                "manager.cicd.skao.int/managed": "true",
                "cicd.skao.int/status": "stale",
            }
        )
        for namespace in stale_namespaces:
            if namespace.status.phase == "Terminating":
                logging.debug(
                    "Namespace %s is already terminating",
                    namespace.metadata.name,
                )
                continue

            logging.info(
                "Deleting stale namespace %s", namespace.metadata.name
            )
            self.delete_namespace(namespace.metadata.name)

    @controller_task(period=datetime.timedelta(seconds=1))
    def delete_failed_namespaces(self) -> None:
        """
        Looks for namespaces with failed status and deletes them.
        :return:
        """
        failed_namespaces = self.get_namespaces_by(
            annotations={
                "manager.cicd.skao.int/managed": "true",
                "cicd.skao.int/status": "failed",
            }
        )
        for namespace in failed_namespaces:
            if namespace.status.phase == "Terminating":
                logging.debug(
                    "Namespace %s is already terminating",
                    namespace.metadata.name,
                )
                continue

            logging.info(
                "Deleting failed namespace %s", namespace.metadata.name
            )
            self.delete_namespace(namespace.metadata.name)
