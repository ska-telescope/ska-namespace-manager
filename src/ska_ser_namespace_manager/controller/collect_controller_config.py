"""
collect_controller_config centralizes all the configuration loading
for the collect controller component
"""

from pydantic import BaseModel

from ska_ser_namespace_manager.controller.controller_config import (
    ControllerConfig,
)


class CollectNamespaceConfig(BaseModel):
    """
    CollectNamespaceConfig holds the namespace collection configuration.
    Since the collectors will annotate the namespaces with the infered
    states, it needs to know how to characterize a given namespace
    """


class CollectControllerConfig(ControllerConfig):
    """
    CollectControllerConfig is a singleton class to provide abstraction
    from configuration loading for the CollectController
    """

    namespaces: list[CollectNamespaceConfig]
