"""
This module provides the a generic LeaderController class to build
other controllers with leader election

Usage:
    To use this module, create an instance of LeaderController or inherit
    from it and call the run() method.
    Example:
        LeaderController().run()
"""

import datetime
import threading

from ska_ser_namespace_manager.controller.controller import (
    Controller,
    ControllerTask,
)
from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)
from ska_ser_namespace_manager.controller.leader_lock import LeaderLock


class LeaderController(Controller):
    """
    A generic controller class to implement simple process
    management tasks with leader election
    """

    leader_lock: LeaderLock

    def __init__(
        self, config_class: type, tasks: list[callable] | None
    ) -> None:
        """
        Initialize the Controller

        :param config_class: Class to use to load configs
        :param tasks: List of tasks to manage
        """
        super().__init__(config_class, tasks)
        self.config: LeaderControllerConfig
        self.leader_lock = None
        if self.config.leader_election.enabled:
            self.leader_lock = LeaderLock(
                lock_path=self.config.leader_election.lock_path,
                lease_path=self.config.leader_election.lease_path,
                lease_ttl=self.config.leader_election.lease_ttl,
            )
            self.threads["__acquire_lease"] = threading.Thread(
                target=self.__acquire_lease
            )

    def __acquire_lease_period(self) -> datetime.timedelta:
        return max(
            self.config.leader_election.lease_ttl.total_seconds() - 1, 0.5
        )

    @ControllerTask(period=__acquire_lease_period)
    def __acquire_lease(self) -> None:
        if self.leader_lock:
            self.leader_lock.acquire_lease()

    def cleanup(self) -> None:
        super().cleanup()
        self.leader_lock.release()

    def is_leader(self):
        """
        Tells if this controller is the leader or not

        :return: True if controller is the leader, False otherwise
        """
        return self.leader_lock and self.leader_lock.is_leader()
