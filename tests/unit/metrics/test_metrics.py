import os

import pytest
from kubernetes.client import V1Namespace, V1ObjectMeta
from prometheus_client import generate_latest

from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.metrics.metrics import MetricsManager
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig

TEST_METRICS_PATH = os.path.join("tests", "metrics")


@pytest.fixture
def temp_metrics_path():
    metrics_folder = TEST_METRICS_PATH
    metrics_file = os.path.join(metrics_folder, "metrics.prom")
    if os.path.exists(metrics_file):
        os.remove(metrics_file)

    if not os.path.exists(metrics_folder):
        os.makedirs(metrics_folder)

    yield metrics_folder


@pytest.fixture
def metrics_manager():
    manager = MetricsManager(MetricsConfig(registry_path=TEST_METRICS_PATH))
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


def test_update_metrics(metrics_manager):
    test_namespace = V1Namespace(
        metadata=V1ObjectMeta(
            name="test-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILING.value  # pylint: disable=line-too-long # noqa: E501
            },
        )
    )
    metrics_manager.update_namespace_metrics(test_namespace)

    metrics = generate_latest(metrics_manager.registry).decode("utf-8")
    parsed_metrics = parse_metrics_output(metrics)

    expected_labels = {
        "environment": "dev",
        "project": "marvin",
        "team": "system",
        "user": "marvin",
        "pipelineId": "123456",
        "projectId": "654321",
        "namespace": "test-namespace",
    }
    assert (
        parsed_metrics["namespace_manager_ns_status"]["labels"]
        == expected_labels
    )
    assert parsed_metrics["namespace_manager_ns_status"]["value"] == 2.0


def test_save_metrics(metrics_manager, temp_metrics_path):
    test_namespace = V1Namespace(
        metadata=V1ObjectMeta(
            name="test-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "0123456",
                CicdAnnotations.PROJECT_ID.value: "0654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value  # pylint: disable=line-too-long # noqa: E501
            },
        )
    )
    metrics_manager.update_namespace_metrics(test_namespace)
    metrics_manager.save_metrics()

    metrics_file = os.path.join(temp_metrics_path, "metrics.prom")

    with open(metrics_file, "r", encoding="utf-8") as f:
        contents = f.read()
        parsed_metrics = parse_metrics_output(contents)

    expected_labels = {
        "environment": "dev",
        "project": "marvin",
        "team": "system",
        "user": "marvin",
        "pipelineId": "0123456",
        "projectId": "0654321",
        "namespace": "test-namespace",
    }
    assert (
        parsed_metrics["namespace_manager_ns_status"]["labels"]
        == expected_labels
    )
    assert parsed_metrics["namespace_manager_ns_status"]["value"] == 0.0


def test_load_metrics(metrics_manager, temp_metrics_path):
    metrics_content = (
        "# HELP namespace_manager_ns_status Namespace status\n"
        "# TYPE namespace_manager_ns_status gaugeq\n"
        'namespace_manager_ns_status{environment="dev",namespace="test-namespace",pipelineId="abc",project="marvin",projectId="123",team="xsystem",user="marvino"} 0.0\n'  # pylint: disable=line-too-long # noqa: E501
    )

    metrics_file = os.path.join(temp_metrics_path, "metrics.prom")
    with open(metrics_file, "w+", encoding="utf-8") as f:
        f.write(metrics_content.strip())

    metrics_manager.load_metrics()

    metrics = generate_latest(metrics_manager.registry).decode("utf-8")
    parsed_metrics = parse_metrics_output(metrics)

    expected_labels = {
        "environment": "dev",
        "project": "marvin",
        "team": "xsystem",
        "user": "marvino",
        "pipelineId": "abc",
        "projectId": "123",
        "namespace": "test-namespace",
    }
    assert (
        parsed_metrics["namespace_manager_ns_status"]["labels"]
        == expected_labels
    )
    assert parsed_metrics["namespace_manager_ns_status"]["value"] == 0.0
