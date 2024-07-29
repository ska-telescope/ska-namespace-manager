"""
collect_controller_config centralizes all the configuration loading
for the collect controller component
"""

from pydantic import BaseModel

from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)


class CollectNamespaceConfig(BaseModel):
    """
    CollectNamespaceConfig holds the namespace collection configuration.
    Since the collectors will annotate the namespaces with the infered
    states, it needs to know how to characterize a given namespace
    """


class CollectControllerConfig(LeaderControllerConfig):
    """
    CollectControllerConfig is a singleton class to provide abstraction
    from configuration loading for the CollectController
    """

    namespaces: list[CollectNamespaceConfig]
