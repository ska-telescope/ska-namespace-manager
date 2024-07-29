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

from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectControllerConfig,
)
from ska_ser_namespace_manager.controller.controller import (
    ConditionalControllerTask,
    ControllerTask,
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
        super().__init__(CollectControllerConfig, [self.collect, self.leader])

    @ControllerTask(period=datetime.timedelta(milliseconds=1000))
    def collect(self) -> None:
        """
        Dummy task
        """
        logging.info("CollectController task")

    @ConditionalControllerTask(
        period=datetime.timedelta(milliseconds=5000),
        run_if=LeaderController.is_leader,
    )
    def leader(self) -> None:
        """
        Dummy task
        """
        logging.info("CollectController leader task: %s", self.is_leader())
