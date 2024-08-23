"""
metrics provides a singleton wrapper for the MetricsManager
"""

from ska_ser_namespace_manager.api.api_config import APIConfig
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.utils import Singleton
from ska_ser_namespace_manager.metrics.metrics import MetricsManager
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


class Metrics(metaclass=Singleton):  # pragma: no cover
    """
    Metrics wraps MetricsManager in a singleton class
    """

    config: MetricsConfig
    metrics_manager: MetricsManager

    def __init__(self) -> None:
        """
        Initializes people database singleton wrapper

        :return:
        """
        config: APIConfig = ConfigLoader().load(APIConfig)
        self.config = config.metrics
        self.metrics_manager = MetricsManager(self.config)

    def get_metrics(self):
        """
        Get the latest metrics
        """
        return self.metrics_manager.get_metrics()
