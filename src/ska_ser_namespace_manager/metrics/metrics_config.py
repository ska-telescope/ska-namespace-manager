"""
metrics_config holds the configuration class for the metrics module
"""

from pydantic import BaseModel


class MetricsConfig(BaseModel):
    """
    MetricsConfig holds configuration for the metrics module
    
    * enabled: True to enable metrics, False to disable
    * cache_ttl: Cache TTL in seconds for generated metrics
    """

    enabled: bool = True
    cache_ttl: int = 15
