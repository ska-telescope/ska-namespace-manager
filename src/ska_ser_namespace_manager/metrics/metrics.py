"""
Module for managing the metrics reported by the Prometheus Exporter.
"""

import os
from typing import TypeVar

from prometheus_client import (
    CollectorRegistry,
    Gauge,
    generate_latest,
    write_to_textfile,
)

from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.utils import Singleton
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig

T = TypeVar("T", bound=MetricsConfig)


class MetricsManager(metaclass=Singleton):
    """Singleton class that groups all the metrics."""

    __allow_reinitialization = False

    def __init__(self, config_class: T = MetricsConfig):
        self.config: T = ConfigLoader().load(config_class)

        logging.info("Saving metrics to: %s", self.config.metrics.metrics_path)

        if not os.path.exists(self.config.metrics.metrics_path):
            os.makedirs(self.config.metrics.metrics_path)

        self.metrics_file = self.config.metrics.metrics_path + "/metrics.prom"
        self.registry = CollectorRegistry()

        self.namespace_manager_ns_count = Gauge(
            name="namespace_manager_ns_count",
            documentation="Number of namespaces",
            labelnames=[
                "team",
                "project",
                "user",
                "environment",
                "namespace",
            ],
            registry=self.registry,
        )
        # Track the metrics we set to facilitate stale gauge deletion
        self.set_metrics = set()

        self.load_metrics()

    def set_gauge(self, gauge: Gauge, amount: int = 1, **labels) -> None:
        """
        Increment the value of a Prometheus Gauge metric.
        """
        if labels:
            gauge.labels(**labels).set(amount)
            # Track this gauge to facilitate stale gauge deletion
            self.set_metrics.add(tuple(sorted(labels.items())))
        else:
            gauge.set(amount)

    def get_metrics(self) -> None:
        """
        Generate the latest metrics from the Prometheus registry.

        This method collects all the current metrics from the Prometheus
        registry and returns them in a format that Prometheus can scrape.

        :returns: A bytes object containing the latest metrics.
        """
        self.load_metrics()
        return generate_latest(self.registry)

    def save_metrics(self):
        """
        Save the current metrics to a file.

        This method writes the current metrics to a file in a format
        that Prometheus can read.
        """
        logging.debug(
            "Saving prometheus metrics to file %s", self.metrics_file
        )
        write_to_textfile(self.metrics_file, self.registry)

    def load_metrics(self):
        """
        Load metrics from a file.

        This method reads metrics from a file and updates the in-memory
        metrics with the values from the file.
        """
        if os.path.exists(self.metrics_file):
            logging.debug(
                "Loading prometheus metrics from %s", self.metrics_file
            )
            with open(self.metrics_file, "r", encoding="utf-8") as f:
                for line in f:
                    # Skip comment lines and metadata lines
                    if line.startswith("#"):
                        continue
                    # Process only lines with metric values
                    if " " in line:
                        metric, value = line.split(" ")
                        value = float(value)
                        # Check if metric has labels
                        if "{" in metric:
                            name, labels = metric.split("{")
                            labels = labels.rstrip("}")
                            label_dict = dict(
                                item.split("=") for item in labels.split(",")
                            )
                            label_dict = {
                                k: v.strip('"') for k, v in label_dict.items()
                            }
                            # Update the metric in the registry
                            self.update_metric(name, label_dict, value)
                            # Track the loaded metric in set_metrics
                            self.set_metrics.add(
                                tuple(sorted(label_dict.items()))
                            )

    def update_metric(self, name: str, labels: dict, value: float):
        """
        Update the metric with the given name, labels, and value.
        """
        if name == "namespace_manager_ns_count":
            self.namespace_manager_ns_count.labels(**labels).set(value)
