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
import logging

from ska_ser_namespace_manager.controller.action_controller_config import (
    ActionControllerConfig,
)
from ska_ser_namespace_manager.controller.controller import (
    ConditionalControllerTask,
    ControllerTask,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)


class ActionController(LeaderController):
    """
    ActionController is responsible for creating tasks to perform actions
    on managed resources and manage those tasks
    """

    def __init__(self) -> None:
        """
        Initialize the CollectController
        """
        super().__init__(ActionControllerConfig, [self.act])

    @ControllerTask(period=datetime.timedelta(milliseconds=1000))
    def act(self) -> None:
        """
        Dummy task
        """
        logging.info("ActionController task")

    @ConditionalControllerTask(
        period=datetime.timedelta(milliseconds=5000),
        run_if=LeaderController.is_leader,
    )
    def leader(self) -> None:
        """
        Dummy task
        """
        logging.info("ActionController leader task: %s", self.is_leader())
