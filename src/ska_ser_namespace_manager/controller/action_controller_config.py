"""
action_controller_config centralizes all the configuration loading
for the action controller component
"""

from typing import List, Optional

from pydantic import BaseModel

from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)
from ska_ser_namespace_manager.core.namespace import NamespaceMatcher


class ActionNamespacePhaseConfig(BaseModel):
    """
    ActionNamespacePhaseConfig holds specific action information
    for a particular phase of the namespace

    * delete: Delete when in phase
    * notify_on_delete: Notify the owner when namespace is deleted on
    """

    delete: bool = True
    notify_on_delete: bool = True


class ActionNamespaceConfig(NamespaceMatcher):
    """
    ActionNamespaceConfig holds the configurations to a namespace group
    being acted on.

    * stale: Configuration on how to act on stale namespaces
    * failed: Configuration on how to act on stale namespaces
    """

    stale: ActionNamespacePhaseConfig = ActionNamespacePhaseConfig()
    failed: ActionNamespacePhaseConfig = ActionNamespacePhaseConfig()


class NotifierConfig(BaseModel):
    """
    NotificationsConfig holds configurations to govern how we notify
    users. For now, it assumes slack notifications

    * token: Slack App bot token
    """

    token: Optional[str] = None


class ActionControllerConfig(LeaderControllerConfig):
    """
    ActionControllerConfig is a singleton class to provide abstraction
    from configuration loading for the ActionController
    """

    namespaces: List[ActionNamespaceConfig]
    notifier: NotifierConfig = NotifierConfig()
