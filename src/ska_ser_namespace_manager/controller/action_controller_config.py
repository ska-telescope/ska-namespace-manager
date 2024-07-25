"""
action_controller_config centralizes all the configuration loading
for the action controller component
"""

import datetime
from typing import Annotated, List

from pydantic import BaseModel, BeforeValidator

from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)
from ska_ser_namespace_manager.core.namespace import NamespaceMatcher
from ska_ser_namespace_manager.core.utils import parse_timedelta


class ActionNamespacePhaseConfig(BaseModel):
    """
    ActionNamespacePhaseConfig holds specific action information
    for a particular phase of the namespace

    * delete: Delete when in phase
    * notify_on_delete: Notify the owner when namespace enters the phase
    * delete_grace_period: Grace period after notifying the owner until the
    actual action takes place
    """

    delete: bool = True
    notify_on_delete: bool = True
    delete_grace_period: Annotated[
        datetime.timedelta, BeforeValidator(parse_timedelta)
    ] = datetime.timedelta(seconds=0)


class ActionNamespaceConfig(NamespaceMatcher):
    """
    ActionNamespaceConfig holds the configurations to a namespace group
    being acted on.

    * stale: Configuration on how to act on stale namespaces
    * failed: Configuration on how to act on stale namespaces
    """

    stale: ActionNamespacePhaseConfig = ActionNamespacePhaseConfig()
    failed: ActionNamespacePhaseConfig = ActionNamespacePhaseConfig()


class ActionControllerConfig(LeaderControllerConfig):
    """
    ActionControllerConfig is a singleton class to provide abstraction
    from configuration loading for the ActionController
    """

    namespaces: List[ActionNamespaceConfig]
