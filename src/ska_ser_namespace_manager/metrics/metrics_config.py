"""
metrics_config holds the configuration class for the metrics module
"""

from pydantic import BaseModel


class MetricsConfig(BaseModel):
    """
    MetricsConfig holds configuration for the metrics module

    * registry_path: Path to the folder holding the metrics registry
    * enabled: True to enable metrics, False to disable
    """

    registry_path: str = "metrics"
    enabled: bool = True
