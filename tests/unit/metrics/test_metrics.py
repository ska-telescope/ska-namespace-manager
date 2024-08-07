import os

import pytest
from prometheus_client import generate_latest

from ska_ser_namespace_manager.metrics.metrics import MetricsManager


@pytest.fixture
def temp_metrics_path():
    metrics_folder = "tests/metrics/"
    if os.path.exists(metrics_folder + "metrics.prom"):
        os.remove(metrics_folder + "metrics.prom")

    if not os.path.exists(metrics_folder):
        os.makedirs(metrics_folder)
    yield metrics_folder


@pytest.fixture
def metrics_manager():
    """Fixture to initialize the MetricsManager with the temporary path."""
    manager = MetricsManager()
    manager.metrics_file = "tests/metrics/metrics.prom"
    yield manager


def parse_metrics_output(metrics_output):
    """
    Parse Prometheus metrics output into a dictionary for easier comparison.

    :param metrics_output: Raw string output of Prometheus metrics
    :return: A dictionary with metric names as keys and another dictionary
             of label-value pairs as values.
    """
    metrics_dict = {}
    lines = metrics_output.strip().splitlines()
    for line in lines:
        if line.startswith("#"):
            continue
        metric, value = line.split(" ")
        value = float(value)
        if "{" in metric:
            name, labels = metric.split("{")
            labels = labels.rstrip("}")
            label_dict = dict(item.split("=") for item in labels.split(","))
            label_dict = {k: v.strip('"') for k, v in label_dict.items()}
        else:
            name = metric
            label_dict = {}
        metrics_dict[name] = {"labels": label_dict, "value": value}
    return metrics_dict


def test_set_gauge(metrics_manager):
    """Test setting a gauge metric."""
    metrics_manager.set_gauge(
        metrics_manager.namespace_manager_ns_count,
        amount=2,
        team="team1",
        project="project1",
        user="user1",
        environment="dev",
        namespace="ns1",
    )

    metrics = generate_latest(metrics_manager.registry).decode("utf-8")
    parsed_metrics = parse_metrics_output(metrics)

    expected_labels = {
        "team": "team1",
        "project": "project1",
        "user": "user1",
        "environment": "dev",
        "namespace": "ns1",
    }
    assert (
        parsed_metrics["namespace_manager_ns_count"]["labels"]
        == expected_labels
    )
    assert parsed_metrics["namespace_manager_ns_count"]["value"] == 2.0


def test_save_metrics(metrics_manager, temp_metrics_path):
    """Test saving metrics to a file."""
    metrics_manager.set_gauge(
        metrics_manager.namespace_manager_ns_count,
        amount=2,
        team="team1",
        project="project1",
        user="user1",
        environment="dev",
        namespace="ns1",
    )
    metrics_manager.save_metrics()

    metrics_file = os.path.join(temp_metrics_path, "metrics.prom")

    with open(metrics_file, "r", encoding="utf-8") as f:
        contents = f.read()
        parsed_metrics = parse_metrics_output(contents)

    expected_labels = {
        "team": "team1",
        "project": "project1",
        "user": "user1",
        "environment": "dev",
        "namespace": "ns1",
    }
    assert (
        parsed_metrics["namespace_manager_ns_count"]["labels"]
        == expected_labels
    )
    assert parsed_metrics["namespace_manager_ns_count"]["value"] == 2.0


def test_load_metrics(metrics_manager, temp_metrics_path):
    """Test loading metrics from a file."""
    # Prepare the metrics file content

    metrics_content = (
        "# HELP namespace_manager_ns_count Number of namespaces"
        "# TYPE namespace_manager_ns_count gauge"
        'namespace_manager_ns_count{team="team1",project="project1",user="user1",environment="dev",status="ok",namespace="ns1"} 2.0'  # pylint: disable=line-too-long # noqa: E501
    )

    metrics_file = os.path.join(temp_metrics_path, "metrics.prom")
    with open(metrics_file, "w", encoding="utf-8") as f:
        f.write(metrics_content.strip())

    metrics_manager.load_metrics()

    metrics = generate_latest(metrics_manager.registry).decode("utf-8")
    parsed_metrics = parse_metrics_output(metrics)

    expected_labels = {
        "team": "team1",
        "project": "project1",
        "user": "user1",
        "environment": "dev",
        "namespace": "ns1",
    }
    assert (
        parsed_metrics["namespace_manager_ns_count"]["labels"]
        == expected_labels
    )
    assert parsed_metrics["namespace_manager_ns_count"]["value"] == 2.0


def test_update_metric(metrics_manager):
    """Test updating a metric."""
    labels = {
        "team": "team1",
        "project": "project1",
        "user": "user1",
        "environment": "dev",
        "namespace": "ns1",
    }
    metrics_manager.update_metric(
        name="namespace_manager_ns_count", labels=labels, value=5.0
    )

    metrics = generate_latest(metrics_manager.registry).decode("utf-8")
    parsed_metrics = parse_metrics_output(metrics)

    assert parsed_metrics["namespace_manager_ns_count"]["labels"] == labels
    assert parsed_metrics["namespace_manager_ns_count"]["value"] == 5.0
