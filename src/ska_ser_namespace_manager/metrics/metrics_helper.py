"""
Helpers for Prometheus metric persistence and restoration.
"""

from pathlib import Path
from typing import Dict, TypeVar, cast

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Enum,
    Gauge,
    Histogram,
    Info,
    Summary,
    write_to_textfile,
)
from prometheus_client.parser import text_string_to_metric_families
from prometheus_client.registry import Collector

from ska_ser_namespace_manager.core.logging import logging

MetricT = TypeVar("MetricT", bound=Collector)


class PrometheusMetricsHelper:
    """
    Helper class for low-level prometheus_client persistence details.
    """

    @staticmethod
    def _build_metric_restore_map(
        metrics: Dict[str, Collector],
    ) -> Dict[str, tuple[Collector, str]]:
        """
        Build a lookup for parsed Prometheus families and expected types.
        """
        restore_map = {}
        for metric in metrics.values():
            for family in metric.collect():
                restore_map[family.name] = (metric, family.type)
                if isinstance(metric, Info):
                    restore_map[f"{family.name}_info"] = (metric, "gauge")
                if isinstance(metric, Enum):
                    restore_map[family.name] = (metric, "gauge")

        return restore_map

    @staticmethod
    def _get_sample_labels(metric: Collector, labels: dict[str, str]) -> dict[str, str]:
        """
        Get labels that belong to the collector rather than the sample.
        """
        return {
            label_name: labels[label_name]
            for label_name in PrometheusMetricsHelper.get_label_names(metric)
        }

    @staticmethod
    def _get_metric_child(metric: MetricT, labels: dict[str, str]) -> MetricT:
        """
        Get the metric child for a sample label set.
        """
        if PrometheusMetricsHelper.get_label_names(metric):
            return cast(MetricT, metric.labels(**labels))

        return metric

    @staticmethod
    def _set_metric_value(metric, value: float) -> None:
        """
        Set a prometheus_client value object.
        """
        metric_value = getattr(metric, "_value")
        metric_value.set(value)

    @staticmethod
    def _restore_gauge_samples(metric: Gauge, family) -> None:
        """
        Restore Gauge samples from a parsed Prometheus metric family.
        """
        for sample in family.samples:
            labels = PrometheusMetricsHelper._get_sample_labels(metric, sample.labels)
            child = PrometheusMetricsHelper._get_metric_child(metric, labels)
            child.set(sample.value)

    @staticmethod
    def _restore_counter_samples(metric: Counter, family) -> None:
        """
        Restore Counter samples from a parsed Prometheus metric family.
        """
        for sample in family.samples:
            if not sample.name.endswith("_total"):
                continue

            labels = PrometheusMetricsHelper._get_sample_labels(metric, sample.labels)
            child = PrometheusMetricsHelper._get_metric_child(metric, labels)
            PrometheusMetricsHelper._set_metric_value(child, sample.value)

    @staticmethod
    def _restore_summary_samples(metric: Summary, family) -> None:
        """
        Restore Summary samples from a parsed Prometheus metric family.
        """
        for sample in family.samples:
            labels = PrometheusMetricsHelper._get_sample_labels(metric, sample.labels)
            child = PrometheusMetricsHelper._get_metric_child(metric, labels)
            if sample.name.endswith("_count"):
                getattr(child, "_count").set(sample.value)
            if sample.name.endswith("_sum"):
                getattr(child, "_sum").set(sample.value)

    @staticmethod
    def _parse_histogram_bound(value: str) -> float:
        """
        Parse a Prometheus histogram bucket boundary.
        """
        if value == "+Inf":
            return float("inf")

        return float(value)

    @staticmethod
    def _restore_histogram_group(
        metric: Histogram,
        labels: dict[str, str],
        bucket_values: dict[float, float],
        sample_sum: float | None,
    ) -> None:
        """
        Restore one Histogram label group from cumulative bucket samples.
        """
        child = PrometheusMetricsHelper._get_metric_child(metric, labels)
        previous_value = 0.0
        buckets = getattr(child, "_buckets")
        upper_bounds = getattr(child, "_upper_bounds")
        for index, upper_bound in enumerate(upper_bounds):
            if upper_bound not in bucket_values:
                logging.warning(
                    "Missing histogram bucket '%s' for metric '%s'",
                    upper_bound,
                    PrometheusMetricsHelper.get_metric_family_name(metric),
                )
                return

            bucket_value = bucket_values[upper_bound] - previous_value
            buckets[index].set(bucket_value)
            previous_value = bucket_values[upper_bound]

        if sample_sum is not None:
            getattr(child, "_sum").set(sample_sum)

    @staticmethod
    def _restore_histogram_samples(metric: Histogram, family) -> None:
        """
        Restore Histogram samples from a parsed Prometheus metric family.
        """
        groups: dict[
            tuple[tuple[str, str], ...],
            tuple[dict[float, float], float | None],
        ] = {}
        for sample in family.samples:
            labels = PrometheusMetricsHelper._get_sample_labels(metric, sample.labels)
            group_key = tuple(sorted(labels.items()))
            bucket_values, sample_sum = groups.get(group_key, ({}, None))
            if sample.name.endswith("_bucket"):
                bucket_values[
                    PrometheusMetricsHelper._parse_histogram_bound(sample.labels["le"])
                ] = sample.value
            if sample.name.endswith("_sum"):
                sample_sum = sample.value

            groups[group_key] = (bucket_values, sample_sum)

        for group_key, group_values in groups.items():
            PrometheusMetricsHelper._restore_histogram_group(
                metric, dict(group_key), *group_values
            )

    @staticmethod
    def _restore_info_samples(metric: Info, family) -> None:
        """
        Restore Info samples from a parsed Prometheus metric family.
        """
        label_names = set(PrometheusMetricsHelper.get_label_names(metric))
        for sample in family.samples:
            labels = PrometheusMetricsHelper._get_sample_labels(metric, sample.labels)
            info_labels = {
                key: value
                for key, value in sample.labels.items()
                if key not in label_names
            }
            child = PrometheusMetricsHelper._get_metric_child(metric, labels)
            child.info(info_labels)

    @staticmethod
    def _restore_enum_samples(metric: Enum, family) -> None:
        """
        Restore Enum samples from a parsed Prometheus metric family.
        """
        family_name = PrometheusMetricsHelper.get_metric_family_name(metric)
        for sample in family.samples:
            if sample.value != 1:
                continue

            labels = PrometheusMetricsHelper._get_sample_labels(metric, sample.labels)
            child = PrometheusMetricsHelper._get_metric_child(metric, labels)
            child.state(sample.labels[family_name])

    @staticmethod
    def _restore_metric_samples(metric: Collector, family) -> None:
        """
        Restore parsed samples into a registered collector.
        """
        if isinstance(metric, Gauge):
            PrometheusMetricsHelper._restore_gauge_samples(metric, family)
            return

        if isinstance(metric, Counter):
            PrometheusMetricsHelper._restore_counter_samples(metric, family)
            return

        if isinstance(metric, Summary):
            PrometheusMetricsHelper._restore_summary_samples(metric, family)
            return

        if isinstance(metric, Histogram):
            PrometheusMetricsHelper._restore_histogram_samples(metric, family)
            return

        if isinstance(metric, Info):
            PrometheusMetricsHelper._restore_info_samples(metric, family)
            return

        if isinstance(metric, Enum):
            PrometheusMetricsHelper._restore_enum_samples(metric, family)
            return

        logging.warning(
            "Unsupported collector type '%s' for metric '%s'",
            type(metric).__name__,
            family.name,
        )

    @staticmethod
    def get_metric_family_name(collector: Collector) -> str:
        """
        Get the Prometheus metric family name for a registered collector.
        """
        return next(iter(collector.collect())).name

    @staticmethod
    def get_label_names(metric: Collector) -> tuple[str, ...]:
        """
        Get configured collector label names.
        """
        return tuple(getattr(metric, "_labelnames", ()))

    @staticmethod
    def restore_metrics(
        metrics: Dict[str, Collector],
        metrics_content: str,
    ) -> None:
        """
        Restore known metric samples from Prometheus text content.
        """
        restore_map = PrometheusMetricsHelper._build_metric_restore_map(metrics)
        for family in text_string_to_metric_families(metrics_content):
            if family.name.endswith("_created"):
                base_name = family.name[: -len("_created")]
                if base_name in restore_map:
                    continue

            metric_definition = restore_map.get(family.name)
            if metric_definition is None:
                logging.warning("Unrecognized or unsupported metric: %s", family.name)
                continue

            metric, expected_type = metric_definition
            if family.type != expected_type:
                logging.warning(
                    "Unsupported metric type '%s' for metric '%s'",
                    family.type,
                    family.name,
                )
                continue

            PrometheusMetricsHelper._restore_metric_samples(metric, family)

    @staticmethod
    def restore_metrics_file(
        metrics: Dict[str, Collector],
        metrics_file: str | Path,
    ) -> None:
        """
        Restore metrics from a Prometheus textfile.
        """
        with open(metrics_file, "r", encoding="utf-8") as file_handle:
            PrometheusMetricsHelper.restore_metrics(metrics, file_handle.read())

    @staticmethod
    def write_metrics_file(
        registry: CollectorRegistry, metrics_file: str | Path
    ) -> None:
        """
        Write a registry to a Prometheus textfile.
        """
        write_to_textfile(str(metrics_file), registry)
