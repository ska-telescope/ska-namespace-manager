"""
Module for managing the metrics reported by the Prometheus Exporter.
"""

import os
from typing import Dict

from kubernetes.client import V1Namespace
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    write_to_textfile,
)
from prometheus_client.registry import Collector

from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


class MetricsManager:
    """Singleton class that groups all the metrics."""

    metrics: Dict[str, Collector]

    def __init__(self, config: MetricsConfig):
        self.config = config
        logging.info("Metrics regsitry at: %s", self.config.registry_path)

        if not os.path.exists(self.config.registry_path):
            os.makedirs(self.config.registry_path)

        self.metrics_file = os.path.join(
            self.config.registry_path, "metrics.prom"
        )
        self.load_metrics()

    def delete_stale_metrics(self, namespaces: list[str]):
        """
        Delete metrics on namespaces that no longer exist

        :param namespaces: Existing namespaces
        """
        for (
            sample
        ) in (
            self.namespace_manager_ns_status._samples()  # pylint: disable=line-too-long,protected-access  # noqa: E501
        ):
            namespace = sample.labels.get("namespace")
            if namespace not in namespaces:
                logging.info("Removed metrics for namespace '%s'", namespace)
                self.namespace_manager_ns_status.remove(
                    *sample.labels.values()
                )

    def update_namespace_metrics(self, namespace: V1Namespace):
        """
        Update namespace metric on namespaces that no longer exist

        :param namespace: Namespace to update metrics on
        """
        labels = namespace.metadata.labels or {}
        annotations = namespace.metadata.annotations or {}
        status = annotations.get(NamespaceAnnotations.STATUS.value, "unknown")
        status_numeric = NamespaceStatus.from_string(status).value_numeric

        self.namespace_manager_ns_status.labels(
            environment=labels.get(CicdAnnotations.ENV_TIER.value, "unknown"),
            project=labels.get(CicdAnnotations.PROJECT.value, "unknown"),
            team=labels.get(CicdAnnotations.TEAM.value, "unknown"),
            user=labels.get(CicdAnnotations.AUTHOR.value, "unknown"),
            pipelineId=labels.get(
                CicdAnnotations.PIPELINE_ID.value, "unknown"
            ),
            projectId=labels.get(CicdAnnotations.PROJECT_ID.value, "unknown"),
            namespace=namespace.metadata.name,
        ).set(status_numeric)

        logging.debug(
            f"Updated metrics for namespace '{namespace.metadata.name}' - "
            f"Status: {status}"
        )

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
        self.load_metrics()
        return generate_latest(self.registry)

    def save_metrics(self):
        """
        Save the current metrics to a file.

        This method writes the current metrics to a file in a format
        that Prometheus can read.
        """
        logging.debug("Saving prometheus metrics to '%s'", self.metrics_file)
        write_to_textfile(self.metrics_file, self.registry)

    def load_metrics(self):
        """
        Load metrics from a file.

        This method reads metrics from a file and updates the in-memory
        metrics with the values from the file.
        """
        self.registry = CollectorRegistry()
        self.namespace_manager_ns_status = Gauge(
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
            registry=self.registry,
        )

        if os.path.exists(self.metrics_file):
            logging.debug(
                "Loading prometheus metrics from %s", self.metrics_file
            )
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("#"):
                        continue

                    if " " in line:
                        metric, value = line.split(" ")
                        value = float(value)
                        if "{" in metric:
                            name, labels = metric.split("{")
                            labels = labels.rstrip("}")
                            label_dict = dict(
                                item.split("=") for item in labels.split(",")
                            )
                            label_dict = {
                                k: v.strip('"') for k, v in label_dict.items()
                            }

                            # TODO: Implement this bit of code in a generic way
                            # to support other collectors
                            gauge = getattr(self, name, None)
                            if gauge and isinstance(gauge, Gauge):
                                gauge.labels(**label_dict).set(value)
                                logging.debug(
                                    f"Set {name} with labels "
                                    f"{label_dict} to {value}"
                                )
                            else:
                                logging.warning(
                                    "Unrecognized or unsupported "
                                    f"metric: {name}"
                                )
