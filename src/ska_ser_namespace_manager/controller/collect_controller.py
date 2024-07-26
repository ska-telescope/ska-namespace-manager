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
import logging

from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectControllerConfig,
)
from ska_ser_namespace_manager.controller.controller import (
    Controller,
    ControllerTask,
)


class CollectController(Controller):
    """
    CollectController is responsible for creating tasks to collect
    information on managed resources and manage those tasks
    """

    def __init__(self) -> None:
        """
        Initialize the CollectController
        """
        super().__init__(CollectControllerConfig, [self.collect])

    @ControllerTask(period=datetime.timedelta(milliseconds=1000))
    def collect(self) -> None:
        """
        Dummy task
        """
        logging.info("CollectController task")
