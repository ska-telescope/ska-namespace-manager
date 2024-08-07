"""
metrics_config holds the configuration class for the metrics module
"""

from pydantic import BaseModel


class MetricsConfig(BaseModel):
    """
    MetricsConfig holds configuration for the metrics module

    * metrics_path: path to the folder holding the metrics
    * update_period: number of seconds between each metric update
    """

    metrics_path: str = "./metrics"
    enabled: bool = True
