"""
collect_controller_config centralizes all the configuration loading
for the collect controller component
"""

import datetime
from typing import Annotated, List

from pydantic import BeforeValidator

from ska_ser_namespace_manager.controller.controller_config import (
    ControllerNamespaceMatcher,
)
from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)
from ska_ser_namespace_manager.core.namespace import NamespaceMatcher
from ska_ser_namespace_manager.core.utils import parse_timedelta


class CollectNamespaceConfig(NamespaceMatcher):
    """
    CollectNamespaceConfig holds the configurations indicating how to
    dictate namespace phases.

    * ttl: Namespace ttl to become stale
    * grace_period: Grace period to mark a failing namespace as failed
    """

    ttl: (
        Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None
    ) = None
    grace_period: (
        Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None
    ) = datetime.timedelta(minutes=1)


class CollectControllerConfig(LeaderControllerConfig):
    """
    CollectControllerConfig is a singleton class to provide abstraction
    from configuration loading for the CollectController
    """

    namespaces: List[CollectNamespaceConfig]
