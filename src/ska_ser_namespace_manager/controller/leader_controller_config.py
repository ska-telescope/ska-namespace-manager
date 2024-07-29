"""
leader_controller_config centralizes all the configurations for
the leader lock process
"""

import datetime
import os
from typing import Annotated, Optional

from pydantic import BaseModel, BeforeValidator

from ska_ser_namespace_manager.controller.controller_config import (
    ControllerConfig,
)
from ska_ser_namespace_manager.core.utils import parse_timedelta


class LeaderElectionConfig(BaseModel):
    """
    LeaderElectionConfig holds configurations for controller leader
    election process
    """

    enabled: bool = False
    path: str = "/etc/leader"
    lock_path: Optional[str] = None
    lease_path: Optional[str] = None
    lease_ttl: Annotated[
        datetime.timedelta, BeforeValidator(parse_timedelta)
    ] = datetime.timedelta(seconds=5)

    def model_post_init(self, _):
        self.lock_path = os.path.join(self.path, "lock")
        self.lease_path = os.path.join(self.path, "lease")


class LeaderControllerConfig(ControllerConfig):
    """
    LeaderControllerConfig holds shared controller configurations
    """

    leader_election: LeaderElectionConfig
