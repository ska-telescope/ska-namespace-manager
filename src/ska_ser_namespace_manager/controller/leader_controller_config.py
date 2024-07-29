"""
controller_config centralizes all the shared configurations
between controllers
"""

import datetime
import os

from pydantic import BaseModel


class LeaderElectionConfig(BaseModel):
    """
    LeaderElectionConfig holds configurations for controller leader
    election process
    """

    enabled: bool = False
    path: str = "/etc/leader"
    lock_path: str | None = None
    lease_path: str | None = None
    lease_ttl: datetime.timedelta = datetime.timedelta(seconds=5)

    def model_post_init(self, _):
        self.lock_path = os.path.join(self.path, "lock")
        self.lease_path = os.path.join(self.path, "lease")


class LeaderControllerConfig(BaseModel):
    """
    LeaderControllerConfig holds shared controller configurations
    """

    leader_election: LeaderElectionConfig
