"""
This module provides the collect controller component. This controller
is responsible for creating tasks to collect information on managed
resources

Usage:
    To use this module, create an instance of CollectController and
    call the run() method.
    Example:
        CollectController().run()
"""

import datetime

import yaml

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
from ska_ser_namespace_manager.core.logging import logging


class CollectController(LeaderController):
    """
    CollectController is responsible for creating tasks to collect
    information on managed resources and manage those tasks
    """

    def __init__(self) -> None:
        """
        Initialize the CollectController
        """
        super().__init__(CollectControllerConfig, [self.check_new_namespaces])
        if self.config.leader_election.enabled:
            self.add_tasks([self.loadbalance_namespaces])

    def create_collect_cronjob(self, namespace: str) -> None:
        """
        Create a new CronJob for the given namespace.

        :param namespace: The namespace to create the CronJob for.
        :type namespace: str
        """
        with open(
            "ska_ser_namespace_manager/collector/resources/cronjob.yaml",
            "r",
            encoding="utf-8",
        ) as file:
            content = file.read()
            content = content.replace("{{namespace}}", namespace)
            cronjob_manifest = yaml.safe_load(content)

        try:
            self.batch_v1.create_namespaced_cron_job(
                "ska-ser-namespace-manager", cronjob_manifest
            )
            logging.info(
                "Collect CronJob for namespace %s created.", namespace
            )
            
        except Exception as e:  # pylint: disable=broad-exception-caught
            logging.error(
                "Exception when creating Collect CronJob for namespace %s: %s",
                namespace,
                e,
            )
            self.terminate()

    @controller_task(period=datetime.timedelta(seconds=1))
    def check_new_namespaces(self) -> None:
        """
        Check for new namespaces and create a CronJob for each new namespace.
        """
        unmanaged_namespaces = self.get_namespaces_by(
            exclude_annotations={"manager.cicd.skao.int/managed": "true"},
            # annotations={"manager.cicd.skao.int/managed_by": "true"}
        )

        for namespace in unmanaged_namespaces:
            namespace = namespace.metadata.name

            self.patch_namespace(
                namespace,
                annotations={"manager.cicd.skao.int/managed": "true"},
            )
            logging.info("New namespace detected: %s", namespace)
            self.create_collect_cronjob(namespace)

    @conditional_controller_task(
        period=datetime.timedelta(milliseconds=500),
        run_if=LeaderController.is_leader,
    )
    def loadbalance_namespaces(self) -> None:
        """
        Lists namespaces which aren't managed and loadbalances
        them between the existing collect controllers.
        """
        # List controllers: list pods in manager namespace, filter by name
        # List all namespaces
        # Check number of namespaces allocated to each
        # controller: manager.cicd.skao.int/managed_by
        # loadbalance namespaces between controllers
        # set manager.cicd.skao.int/managed_by to controller name
