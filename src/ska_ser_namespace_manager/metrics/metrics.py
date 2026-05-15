"""
Module for managing the metrics reported by the Prometheus Exporter.
"""

import os
from pathlib import Path
from threading import RLock
from typing import Dict

from kubernetes.client import V1Namespace
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)
from prometheus_client.registry import Collector

from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig
from ska_ser_namespace_manager.metrics.metrics_helper import (
    PrometheusMetricsHelper,
)


class MetricsManager:
    """Groups and persists metrics for one controller process."""

    metrics: Dict[str, Collector]
    NAMESPACE_STATUS_METRIC_NAME: str = "namespace_manager_ns_status"
    NAMESPACE_CHECK_RESULT_METRIC_NAME: str = (
        "namespace_manager_ns_check_total"
    )
    NAMESPACE_CHECK_RESULTS: tuple[str, str] = ("success", "failure")
    NAMESPACE_DELETE_METRIC_NAME: str = "namespace_manager_ns_delete_total"

    def __init__(self, config: MetricsConfig, owner: str | None = None):
        self.config = config
        self.owner = owner
        self._lock = RLock()
        logging.info("Metrics registry at: %s", self.config.registry_path)

        if not os.path.exists(self.config.registry_path):
            os.makedirs(self.config.registry_path)

        self.metrics_file = os.path.join(
            self.config.registry_path,
            f"{Path(self.owner).name if self.owner else 'metrics'}.prom",
        )

        self._load_metrics()

    @staticmethod
    def build_registry() -> tuple[CollectorRegistry, Dict[str, Collector]]:
        """
        Build the application metrics registry and known collectors.
        """
        registry = CollectorRegistry()
        metrics: Dict[str, Collector] = {}
        metrics[MetricsManager.NAMESPACE_STATUS_METRIC_NAME] = Gauge(
            name=MetricsManager.NAMESPACE_STATUS_METRIC_NAME,
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
        metrics[MetricsManager.NAMESPACE_CHECK_RESULT_METRIC_NAME] = Counter(
            name=MetricsManager.NAMESPACE_CHECK_RESULT_METRIC_NAME,
            documentation=(
                "Number of periodic namespace check executions by result"
            ),
            labelnames=["owner", "result"],
            registry=registry,
        )
        metrics[MetricsManager.NAMESPACE_DELETE_METRIC_NAME] = Counter(
            name=MetricsManager.NAMESPACE_DELETE_METRIC_NAME,
            documentation="Number of namespaces deleted by status",
            labelnames=["owner", "status"],
            registry=registry,
        )

        return registry, metrics

    def _load_metrics(self):
        """
        Load metrics from a file.

        This method reads metrics from a file and updates the in-memory
        metrics with the values from the file.
        """
        with self._lock:
            self.registry, self.metrics = MetricsManager.build_registry()

            if os.path.exists(self.metrics_file):
                logging.debug(
                    "Loading prometheus metrics from %s", self.metrics_file
                )
                PrometheusMetricsHelper.restore_metrics_file(
                    self.metrics, self.metrics_file
                )

    def delete_stale_metrics(self, namespaces: list[str]):
        """
        Delete metrics on namespaces that no longer exist

        :param namespaces: Existing namespaces
        """
        with self._lock:
            metric = self.metrics.get(
                MetricsManager.NAMESPACE_STATUS_METRIC_NAME
            )
            label_names = PrometheusMetricsHelper.get_label_names(metric)
            for sample in next(iter(metric.collect())).samples:
                namespace = sample.labels.get("namespace")
                if namespace not in namespaces:
                    logging.info(
                        "Removed metrics for namespace '%s'", namespace
                    )
                    metric.remove(
                        *[
                            sample.labels[label_name]
                            for label_name in label_names
                        ]
                    )

    def delete_stale_metrics_files(self, pod_names: list[str]) -> list[str]:
        """
        Delete metrics files that do not match active pod names.
        """
        deleted_files = []
        expected_files = {f"{pod_name}.prom" for pod_name in pod_names}
        registry_path = Path(self.config.registry_path)
        if not registry_path.exists():
            return deleted_files

        with self._lock:
            for metrics_file in registry_path.glob("*.prom"):
                if metrics_file.name in expected_files:
                    continue

                try:
                    metrics_file.unlink()
                    deleted_files.append(metrics_file.name)
                    logging.info(
                        "Deleted stale prometheus metrics file '%s'",
                        metrics_file,
                    )
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    logging.error(
                        "Failed to delete stale prometheus metrics file "
                        "'%s': %s",
                        metrics_file,
                        exc,
                    )

        return deleted_files

    def update_namespace_metrics(self, namespace: V1Namespace):
        """
        Update namespace metric on namespaces that no longer exist

        :param namespace: Namespace to update metrics on
        """
        with self._lock:
            metric = self.metrics.get(
                MetricsManager.NAMESPACE_STATUS_METRIC_NAME
            )
            labels = namespace.metadata.labels or {}
            annotations = namespace.metadata.annotations or {}
            status = annotations.get(
                NamespaceAnnotations.STATUS.value, "unknown"
            )
            status_numeric = NamespaceStatus.from_string(status).value_numeric

            metric.labels(
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

        logging.debug(
            f"Updated metrics for namespace '{namespace.metadata.name}' - "
            f"Status: {status}"
        )

    def record_namespace_check_result(self, result: str) -> None:
        """
        Record a periodic namespace check execution result.

        :param result: One of success or failure
        """
        if result not in MetricsManager.NAMESPACE_CHECK_RESULTS:
            raise ValueError(
                f"Invalid namespace check result '{result}'. Expected one of "
                f"{MetricsManager.NAMESPACE_CHECK_RESULTS}"
            )

        with self._lock:
            metric = self.metrics.get(
                MetricsManager.NAMESPACE_CHECK_RESULT_METRIC_NAME
            )
            metric.labels(
                owner=self.owner,
                result=result,
            ).inc()

    def record_namespace_deletion(self, status: str) -> None:
        """
        Record a namespace deletion by namespace status.

        :param status: Namespace status that caused the deletion
        """
        namespace_status = NamespaceStatus.from_string(status)

        with self._lock:
            metric = self.metrics.get(
                MetricsManager.NAMESPACE_DELETE_METRIC_NAME
            )
            metric.labels(
                owner=self.owner,
                status=namespace_status.value,
            ).inc()

    def get_metrics(self) -> None:
        """
        Generate the latest metrics from the Prometheus registry.

        This method collects all the current metrics from the Prometheus
        registry and returns them in a format that Prometheus can scrape.

        :returns: A bytes object containing the latest metrics.
        """
        logging.debug(
            "Generating prometheus metrics from '%s'", self.metrics_file
        )
        with self._lock:
            self._load_metrics()
            return generate_latest(self.registry)

    def save_metrics(self):
        """
        Save the current metrics to a file.

        This method writes the current metrics to a file in a format
        that Prometheus can read.
        """
        logging.debug("Saving prometheus metrics to '%s'", self.metrics_file)
        with self._lock:
            PrometheusMetricsHelper.write_metrics_file(
                self.registry, self.metrics_file
            )

    def get_merged_metrics(self) -> bytes:
        """
        Merge fresh metrics files into a single Prometheus text response.
        """
        registry, metrics = MetricsManager.build_registry()
        registry_path = Path(self.config.registry_path)
        if not registry_path.exists():
            return generate_latest(registry)

        files = sorted(
            registry_path.glob("*.prom"),
            key=lambda metrics_file: metrics_file.stat().st_mtime,
        )
        for metrics_file in files:
            logging.debug("Merging prometheus metrics from '%s'", metrics_file)
            PrometheusMetricsHelper.restore_metrics_file(metrics, metrics_file)

        return generate_latest(registry)
