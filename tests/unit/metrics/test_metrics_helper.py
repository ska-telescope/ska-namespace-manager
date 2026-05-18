"""
Tests for Prometheus metrics helper utilities.
"""

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client.parser import text_string_to_metric_families

from ska_ser_namespace_manager.metrics.metrics_helper import (
    PrometheusMetricsHelper,
)


def parse_metric_samples(metrics_output):
    """
    Parse Prometheus samples by name and full labels.
    """
    if isinstance(metrics_output, bytes):
        metrics_output = metrics_output.decode("utf-8")

    samples = {}
    for family in text_string_to_metric_families(metrics_output):
        for sample in family.samples:
            samples[(sample.name, tuple(sorted(sample.labels.items())))] = (
                sample.value
            )

    return samples


def build_counter_and_histogram_registry():
    """
    Build a test registry with non-Gauge collectors.
    """
    registry = CollectorRegistry()
    metrics = {
        "namespace_manager_test_counter": Counter(
            name="namespace_manager_test_counter",
            documentation="Test counter",
            labelnames=["namespace"],
            registry=registry,
        ),
        "namespace_manager_test_histogram": Histogram(
            name="namespace_manager_test_histogram",
            documentation="Test histogram",
            labelnames=["namespace"],
            buckets=[1.0, 2.0],
            registry=registry,
        ),
    }

    return registry, metrics


def remove_created_samples(samples):
    """
    Remove created timestamp samples from parsed metrics.
    """
    return {
        key: value
        for key, value in samples.items()
        if not key[0].endswith("_created")
    }


def test_get_label_names_returns_configured_labels():
    """
    Label names should be returned in collector declaration order.
    """
    registry = CollectorRegistry()
    metric = Gauge(
        name="namespace_manager_test_gauge",
        documentation="Test gauge",
        labelnames=["namespace", "status"],
        registry=registry,
    )

    assert PrometheusMetricsHelper.get_label_names(metric) == (
        "namespace",
        "status",
    )


def test_restore_metrics_restores_gauge_samples():
    """
    Gauge samples should be restored from Prometheus text content.
    """
    registry = CollectorRegistry()
    metric = Gauge(
        name="namespace_manager_test_gauge",
        documentation="Test gauge",
        labelnames=["namespace"],
        registry=registry,
    )
    metrics_content = (
        "# HELP namespace_manager_test_gauge Test gauge\n"
        "# TYPE namespace_manager_test_gauge gauge\n"
        'namespace_manager_test_gauge{namespace="test-namespace"} 3.0\n'
    )

    PrometheusMetricsHelper.restore_metrics(
        {"namespace_manager_test_gauge": metric}, metrics_content
    )

    samples = parse_metric_samples(generate_latest(registry))
    key = (
        "namespace_manager_test_gauge",
        (("namespace", "test-namespace"),),
    )
    assert samples[key] == 3.0


def test_restore_metrics_restores_counter_and_histogram():
    """
    Counter and Histogram samples should be restored generically.
    """
    source_registry, source_metrics = build_counter_and_histogram_registry()
    source_metrics["namespace_manager_test_counter"].labels(
        namespace="test-namespace"
    ).inc(7)
    source_metrics["namespace_manager_test_histogram"].labels(
        namespace="test-namespace"
    ).observe(0.5)
    source_metrics["namespace_manager_test_histogram"].labels(
        namespace="test-namespace"
    ).observe(3.0)
    metrics_content = generate_latest(source_registry).decode("utf-8")
    restored_registry, restored_metrics = (
        build_counter_and_histogram_registry()
    )

    PrometheusMetricsHelper.restore_metrics(restored_metrics, metrics_content)

    expected_samples = remove_created_samples(
        parse_metric_samples(metrics_content)
    )
    restored_samples = remove_created_samples(
        parse_metric_samples(generate_latest(restored_registry))
    )
    assert restored_samples == expected_samples


def test_restore_metrics_skips_unknown_metric():
    """
    Unknown metric families should be skipped without failing.
    """
    registry = CollectorRegistry()
    metric = Gauge(
        name="namespace_manager_test_gauge",
        documentation="Test gauge",
        registry=registry,
    )
    metrics_content = (
        "# HELP unknown_metric Unknown metric\n"
        "# TYPE unknown_metric gauge\n"
        "unknown_metric 1.0\n"
    )

    PrometheusMetricsHelper.restore_metrics(
        {"namespace_manager_test_gauge": metric}, metrics_content
    )

    samples = parse_metric_samples(generate_latest(registry))
    assert all(sample[0] != "unknown_metric" for sample in samples)


def test_restore_metrics_skips_created_samples():
    """
    Created timestamp helper families should be ignored.
    """
    registry = CollectorRegistry()
    metric = Counter(
        name="namespace_manager_test_counter",
        documentation="Test counter",
        registry=registry,
    )
    metrics_content = (
        "# HELP namespace_manager_test_counter_created Test counter\n"
        "# TYPE namespace_manager_test_counter_created gauge\n"
        "namespace_manager_test_counter_created 123.0\n"
    )

    PrometheusMetricsHelper.restore_metrics(
        {"namespace_manager_test_counter": metric}, metrics_content
    )

    samples = parse_metric_samples(generate_latest(registry))
    assert samples[("namespace_manager_test_counter_total", ())] == 0.0


def test_restore_metrics_skips_type_mismatch():
    """
    Metric families with unexpected types should not be restored.
    """
    registry = CollectorRegistry()
    metric = Gauge(
        name="namespace_manager_test_gauge",
        documentation="Test gauge",
        registry=registry,
    )
    metrics_content = (
        "# HELP namespace_manager_test_gauge Test gauge\n"
        "# TYPE namespace_manager_test_gauge counter\n"
        "namespace_manager_test_gauge_total 9.0\n"
    )

    PrometheusMetricsHelper.restore_metrics(
        {"namespace_manager_test_gauge": metric}, metrics_content
    )

    samples = parse_metric_samples(generate_latest(registry))
    assert samples[("namespace_manager_test_gauge", ())] == 0.0


def test_write_and_restore_metrics_file(tmp_path):
    """
    Helper file wrappers should persist and restore registry metrics.
    """
    source_registry = CollectorRegistry()
    source_metric = Gauge(
        name="namespace_manager_test_gauge",
        documentation="Test gauge",
        labelnames=["namespace"],
        registry=source_registry,
    )
    source_metric.labels(namespace="test-namespace").set(5)
    metrics_file = tmp_path / "metrics.prom"
    restored_registry = CollectorRegistry()
    restored_metric = Gauge(
        name="namespace_manager_test_gauge",
        documentation="Test gauge",
        labelnames=["namespace"],
        registry=restored_registry,
    )

    PrometheusMetricsHelper.write_metrics_file(source_registry, metrics_file)
    PrometheusMetricsHelper.restore_metrics_file(
        {"namespace_manager_test_gauge": restored_metric}, metrics_file
    )

    samples = parse_metric_samples(generate_latest(restored_registry))
    key = (
        "namespace_manager_test_gauge",
        (("namespace", "test-namespace"),),
    )
    assert samples[key] == 5.0
