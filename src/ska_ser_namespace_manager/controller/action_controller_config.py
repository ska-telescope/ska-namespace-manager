"""
action_controller_config centralizes all the configuration loading
for the action controller component
"""

from pydantic import BaseModel

from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)


class ActionNamespaceConfig(BaseModel):
    """
    ActionNamespaceConfig holds the namespace action configuration.
    Actions should act upon resources based on information determined
    by the collectors, although, we can have action specific
    configurations.
    """


class ActionControllerConfig(LeaderControllerConfig):
    """
    ActionControllerConfig is a singleton class to provide abstraction
    from configuration loading for the ActionController
    """

    namespaces: list[ActionNamespaceConfig]
