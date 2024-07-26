"""
controller_config centralizes all the shared configurations
between controllers
"""

from pydantic import BaseModel


class LeaderElectionConfig(BaseModel):
    """
    LeaderElectionConfig holds configurations for controller leader
    election process
    """

    enabled: bool = False
    path: str = "/etc/leader/lock"


class ControllerConfig(BaseModel):
    """
    ControllerConfig holds shared controller configurations
    """

    leader_election: LeaderElectionConfig
