"""
Tests for metrics persistence, restoration, and merging.
"""

import os
import time

import pytest
from kubernetes.client import V1Namespace, V1ObjectMeta
from prometheus_client import generate_latest
from prometheus_client.parser import text_string_to_metric_families

from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.metrics.metrics import MetricsManager
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


@pytest.fixture
def temp_metrics_path(tmp_path):
    yield str(tmp_path)


@pytest.fixture
def metrics_manager(temp_metrics_path):
    manager = MetricsManager(
        MetricsConfig(registry_path=temp_metrics_path),
        owner="collect-controller-0",
    )
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


def parse_metric_samples(metrics_output):
    """
    Parse Prometheus samples by name and full labels.

    :param metrics_output: Raw string or bytes output of Prometheus metrics
    :return: A dictionary keyed by sample name and sorted labels.
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


def namespace_status_sample(namespace: str, status: float):
    """
    Create the expected parsed namespace status sample tuple.
    """
    return (
        (
            "namespace_manager_ns_status",
            tuple(
                sorted(
                    {
                        "environment": "dev",
                        "project": "marvin",
                        "team": "system",
                        "user": "marvin",
                        "pipelineId": "123456",
                        "projectId": "654321",
                        "namespace": namespace,
                    }.items()
                )
            ),
        ),
        status,
    )


def namespace_check_result_sample(owner: str, result: str, count: float):
    """
    Create the expected parsed namespace check result counter sample tuple.
    """
    return (
        (
            "namespace_manager_namespace_check_total",
            tuple(sorted({"owner": owner, "result": result}.items())),
        ),
        count,
    )


def test_update_metrics(metrics_manager):
    """
    Namespace metric updates should set the expected status sample.
    """
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


def test_record_namespace_check_result(metrics_manager):
    """
    Namespace check result updates should increment the expected counter.
    """
    metrics_manager.record_namespace_check_result("success")
    metrics_manager.record_namespace_check_result("failure")

    samples = parse_metric_samples(generate_latest(metrics_manager.registry))
    success_key, success_value = namespace_check_result_sample(
        "collect-controller-0", "success", 1.0
    )
    failure_key, failure_value = namespace_check_result_sample(
        "collect-controller-0", "failure", 1.0
    )

    assert samples[success_key] == success_value
    assert samples[failure_key] == failure_value


def test_record_namespace_check_result_rejects_invalid_result(
    metrics_manager,
):
    """
    Namespace check result updates should reject unknown result labels.
    """
    with pytest.raises(ValueError, match="Invalid namespace check result"):
        metrics_manager.record_namespace_check_result("unknown")


def test_save_metrics(metrics_manager, temp_metrics_path):
    """
    Saving metrics should write the owner-specific textfile.
    """
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

    metrics_file = os.path.join(temp_metrics_path, "collect-controller-0.prom")

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
    """
    Loading metrics should restore known gauge samples from text format.
    """
    metrics_content = (
        "# HELP namespace_manager_ns_status Namespace status\n"
        "# TYPE namespace_manager_ns_status gauge\n"
        'namespace_manager_ns_status{environment="dev",namespace="test-namespace",pipelineId="abc",project="marvin",projectId="123",team="xsystem",user="marvino"} 0.0\n'  # pylint: disable=line-too-long # noqa: E501
    )

    metrics_file = os.path.join(temp_metrics_path, "collect-controller-0.prom")
    with open(metrics_file, "w+", encoding="utf-8") as f:
        f.write(metrics_content.strip())

    metrics_manager._load_metrics()

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


def test_metrics_manager_uses_owner_specific_file(metrics_manager):
    """
    Metrics managers should persist to files named from their owner.
    """
    assert metrics_manager.metrics_file.endswith("collect-controller-0.prom")


def test_metrics_manager_restores_metrics_on_instantiation(
    metrics_manager, temp_metrics_path
):
    """
    A new manager for the same owner should restore existing samples.
    """
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
                NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value
            },
        )
    )
    metrics_manager.update_namespace_metrics(test_namespace)
    metrics_manager.save_metrics()

    restored_manager = MetricsManager(
        MetricsConfig(registry_path=temp_metrics_path),
        owner="collect-controller-0",
    )
    samples = parse_metric_samples(generate_latest(restored_manager.registry))
    key, value = namespace_status_sample("test-namespace", 0.0)

    assert samples[key] == value


def test_metrics_manager_restores_namespace_check_results(
    metrics_manager, temp_metrics_path
):
    """
    A new manager for the same owner should restore check result counters.
    """
    metrics_manager.record_namespace_check_result("success")
    metrics_manager.record_namespace_check_result("success")
    metrics_manager.record_namespace_check_result("failure")
    metrics_manager.save_metrics()

    restored_manager = MetricsManager(
        MetricsConfig(registry_path=temp_metrics_path),
        owner="collect-controller-0",
    )
    samples = parse_metric_samples(generate_latest(restored_manager.registry))
    success_key, success_value = namespace_check_result_sample(
        "collect-controller-0", "success", 2.0
    )
    failure_key, failure_value = namespace_check_result_sample(
        "collect-controller-0", "failure", 1.0
    )

    assert samples[success_key] == success_value
    assert samples[failure_key] == failure_value


def test_delete_stale_metrics_removes_unassigned_namespace(metrics_manager):
    """
    Stale local namespace metrics should be removed from the registry.
    """
    kept_namespace = V1Namespace(
        metadata=V1ObjectMeta(
            name="kept-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value
            },
        )
    )
    stale_namespace = V1Namespace(
        metadata=V1ObjectMeta(
            name="stale-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILED.value
            },
        )
    )
    metrics_manager.update_namespace_metrics(kept_namespace)
    metrics_manager.update_namespace_metrics(stale_namespace)

    metrics_manager.delete_stale_metrics(["kept-namespace"])

    samples = parse_metric_samples(generate_latest(metrics_manager.registry))
    kept_key, kept_value = namespace_status_sample("kept-namespace", 0.0)
    stale_key, _ = namespace_status_sample("stale-namespace", 4.0)
    assert samples[kept_key] == kept_value
    assert stale_key not in samples


def test_get_merged_metrics_reads_multiple_fresh_files(temp_metrics_path):
    """
    The merge helper should combine fresh metrics files.
    """
    config = MetricsConfig(registry_path=temp_metrics_path)
    manager_one = MetricsManager(config, owner="collect-controller-0")
    manager_two = MetricsManager(config, owner="collect-controller-1")
    namespace_one = V1Namespace(
        metadata=V1ObjectMeta(
            name="first-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value
            },
        )
    )
    namespace_two = V1Namespace(
        metadata=V1ObjectMeta(
            name="second-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: (
                    NamespaceStatus.FAILING.value
                )
            },
        )
    )
    manager_one.update_namespace_metrics(namespace_one)
    manager_one.record_namespace_check_result("success")
    manager_two.update_namespace_metrics(namespace_two)
    manager_two.record_namespace_check_result("failure")
    manager_one.save_metrics()
    manager_two.save_metrics()

    samples = parse_metric_samples(MetricsManager(config).get_merged_metrics())
    first_key, first_value = namespace_status_sample("first-namespace", 0.0)
    second_key, second_value = namespace_status_sample("second-namespace", 2.0)
    success_key, success_value = namespace_check_result_sample(
        "collect-controller-0", "success", 1.0
    )
    failure_key, failure_value = namespace_check_result_sample(
        "collect-controller-1", "failure", 1.0
    )

    assert samples[first_key] == first_value
    assert samples[second_key] == second_value
    assert samples[success_key] == success_value
    assert samples[failure_key] == failure_value


def test_get_merged_metrics_keeps_owner_labelled_result_counters(
    temp_metrics_path,
):
    """
    Result counters from different owners should remain distinct.
    """
    config = MetricsConfig(registry_path=temp_metrics_path)
    manager_one = MetricsManager(config, owner="collect-controller-0")
    manager_two = MetricsManager(config, owner="collect-controller-1")
    manager_one.record_namespace_check_result("success")
    manager_one.record_namespace_check_result("success")
    manager_two.record_namespace_check_result("success")
    manager_one.save_metrics()
    manager_two.save_metrics()

    samples = parse_metric_samples(MetricsManager(config).get_merged_metrics())
    first_key, first_value = namespace_check_result_sample(
        "collect-controller-0", "success", 2.0
    )
    second_key, second_value = namespace_check_result_sample(
        "collect-controller-1", "success", 1.0
    )

    assert samples[first_key] == first_value
    assert samples[second_key] == second_value


def test_get_merged_metrics_ignores_stale_files(temp_metrics_path):
    """
    The merge helper should ignore old owner files.
    """
    config = MetricsConfig(
        registry_path=temp_metrics_path, file_stale_after_seconds=1
    )
    fresh_manager = MetricsManager(config, owner="collect-controller-0")
    stale_manager = MetricsManager(config, owner="collect-controller-1")
    fresh_namespace = V1Namespace(
        metadata=V1ObjectMeta(
            name="fresh-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value
            },
        )
    )
    stale_namespace = V1Namespace(
        metadata=V1ObjectMeta(
            name="stale-namespace",
            labels={
                CicdAnnotations.ENV_TIER.value: "dev",
                CicdAnnotations.PROJECT.value: "marvin",
                CicdAnnotations.TEAM.value: "system",
                CicdAnnotations.AUTHOR.value: "marvin",
                CicdAnnotations.PIPELINE_ID.value: "123456",
                CicdAnnotations.PROJECT_ID.value: "654321",
            },
            annotations={
                NamespaceAnnotations.STATUS.value: NamespaceStatus.FAILED.value
            },
        )
    )
    fresh_manager.update_namespace_metrics(fresh_namespace)
    stale_manager.update_namespace_metrics(stale_namespace)
    fresh_manager.save_metrics()
    stale_manager.save_metrics()
    old_timestamp = time.time() - 120
    os.utime(stale_manager.metrics_file, (old_timestamp, old_timestamp))

    samples = parse_metric_samples(MetricsManager(config).get_merged_metrics())
    fresh_key, fresh_value = namespace_status_sample("fresh-namespace", 0.0)
    stale_key, _ = namespace_status_sample("stale-namespace", 4.0)

    assert samples[fresh_key] == fresh_value
    assert stale_key not in samples


def test_get_merged_metrics_uses_newest_duplicate_sample(temp_metrics_path):
    """
    Duplicate samples should keep the value from the newest metrics file.
    """
    config = MetricsConfig(registry_path=temp_metrics_path)
    old_manager = MetricsManager(config, owner="collect-controller-0")
    new_manager = MetricsManager(config, owner="collect-controller-1")
    old_namespace = V1Namespace(
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
                NamespaceAnnotations.STATUS.value: NamespaceStatus.OK.value
            },
        )
    )
    new_namespace = V1Namespace(
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
                NamespaceAnnotations.STATUS.value: (
                    NamespaceStatus.FAILING.value
                )
            },
        )
    )
    old_manager.update_namespace_metrics(old_namespace)
    new_manager.update_namespace_metrics(new_namespace)
    old_manager.save_metrics()
    new_manager.save_metrics()
    old_timestamp = time.time() - 10
    os.utime(old_manager.metrics_file, (old_timestamp, old_timestamp))

    samples = parse_metric_samples(MetricsManager(config).get_merged_metrics())
    key, value = namespace_status_sample("test-namespace", 2.0)

    assert samples[key] == value
