"""
metrics provides annotation-derived metrics for the API
"""

import time

from prometheus_client import CollectorRegistry, Gauge, generate_latest

from ska_ser_namespace_manager.api.api_config import APIConfig
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.kubernetes_api import KubernetesAPI
from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.core.utils import Singleton
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


class Metrics(metaclass=Singleton):  # pragma: no cover
    """
    Metrics exposes a cached Prometheus payload derived from namespace
    annotations and labels.
    """

    config: MetricsConfig

    def __init__(self) -> None:
        """
        Initialize the metrics exporter.
        """
        config: APIConfig = ConfigLoader().load(APIConfig)
        self.config = config.metrics
        self.kubernetes_api = KubernetesAPI()
        self._cached_metrics = b""
        self._cached_at = 0.0

    def _is_cache_valid(self) -> bool:
        """
        Return whether the cached metrics payload is still valid.
        """
        return (
            self._cached_metrics != b""
            and (time.time() - self._cached_at) < self.config.cache_ttl
        )

    def _build_metrics_payload(self) -> bytes:
        """
        Build the metrics payload from the current managed namespaces.
        """
        registry = CollectorRegistry()
        namespace_manager_ns_status = Gauge(
            name="namespace_manager_ns_status",
            documentation="Namespace status",
            labelnames=[
                "environment",
                "project",
                "team",
                "user",
                "pipelineId",
                "projectId",
                "namespace",
            ],
            registry=registry,
        )

        managed_namespaces = self.kubernetes_api.get_namespaces_by(
            annotations={NamespaceAnnotations.MANAGED.value: "true"}
        )
        for namespace in managed_namespaces:
            labels = namespace.metadata.labels or {}
            annotations = namespace.metadata.annotations or {}
            status = annotations.get(
                NamespaceAnnotations.STATUS.value,
                NamespaceStatus.UNKNOWN.value,
            )
            status_numeric = NamespaceStatus.from_string(status).value_numeric
            namespace_manager_ns_status.labels(
                environment=labels.get(
                    CicdAnnotations.ENV_TIER.value, "unknown"
                ),
                project=labels.get(CicdAnnotations.PROJECT.value, "unknown"),
                team=labels.get(CicdAnnotations.TEAM.value, "unknown"),
                user=labels.get(CicdAnnotations.AUTHOR.value, "unknown"),
                pipelineId=labels.get(
                    CicdAnnotations.PIPELINE_ID.value, "unknown"
                ),
                projectId=labels.get(
                    CicdAnnotations.PROJECT_ID.value, "unknown"
                ),
                namespace=namespace.metadata.name,
            ).set(status_numeric)

        return generate_latest(registry)

    def get_metrics(self):
        """
        Get the latest metrics payload.
        """
        if self._is_cache_valid():
            return self._cached_metrics

        self._cached_metrics = self._build_metrics_payload()
        self._cached_at = time.time()
        return self._cached_metrics
