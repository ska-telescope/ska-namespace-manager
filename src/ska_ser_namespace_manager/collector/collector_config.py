"""
collector_config holds configurations for the collectors, which for now
remain shared with the collect controller configurations
"""

from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectConfig,
)
from ska_ser_namespace_manager.controller.controller_config import (
    ControllerConfig,
)


class CollectorConfig(CollectConfig, ControllerConfig):
    """
    CollectorConfig holds configuration for the information collector
    """
