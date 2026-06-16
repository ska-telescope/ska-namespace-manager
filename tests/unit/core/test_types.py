import pytest

from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    CicdLabels,
    NamespaceAnnotations,
    NamespaceStatus,
)


@pytest.mark.parametrize(
    "member, expected",
    [
        (NamespaceAnnotations.MANAGED, "manager.cicd.skao.int/managed"),
        (NamespaceAnnotations.NAMESPACE, "manager.cicd.skao.int/namespace"),
        (NamespaceAnnotations.ACTION, "manager.cicd.skao.int/action"),
        (NamespaceAnnotations.STATUS, "manager.cicd.skao.int/status"),
        (
            NamespaceAnnotations.STATUS_TS,
            "manager.cicd.skao.int/status_timestamp",
        ),
        (
            NamespaceAnnotations.STATUS_TIMEFRAME,
            "manager.cicd.skao.int/status_timeframe",
        ),
        (
            NamespaceAnnotations.STATUS_FINALIZE_AT,
            "manager.cicd.skao.int/status_finalize_at",
        ),
        (
            NamespaceAnnotations.FAILING_RESOURCES,
            "manager.cicd.skao.int/failing_resources",
        ),
        (
            NamespaceAnnotations.NOTIFIED_TS,
            "manager.cicd.skao.int/notified_timestamp",
        ),
        (
            NamespaceAnnotations.NOTIFIED_STATUS,
            "manager.cicd.skao.int/notified_status",
        ),
    ],
)
def test_namespace_annotations_values(member, expected):
    assert str(member) == expected, "Enum value does not match expected string"


@pytest.mark.parametrize(
    "member, expected",
    [
        (CicdAnnotations.AUTHOR_EMAIL, "cicd.skao.int/authorEmail"),
        (CicdAnnotations.ENVIRONMENT, "cicd.skao.int/environment"),
        (CicdAnnotations.JOB_URL, "cicd.skao.int/jobUrl"),
        (CicdAnnotations.MR_ASSIGNEES, "cicd.skao.int/mrAssignees"),
        (
            CicdAnnotations.NOTIFICATION_ADDRESS,
            "cicd.skao.int/notificationAddress",
        ),
        (CicdAnnotations.PIPELINE_URL, "cicd.skao.int/pipelineUrl"),
        (CicdAnnotations.TIMESTAMP, "cicd.skao.int/timestamp"),
    ],
)
def test_cicd_annotations_values(member, expected):
    assert str(member) == expected, "Enum value does not match expected string"


@pytest.mark.parametrize(
    "member, expected",
    [
        (CicdLabels.AUTHOR, "cicd.skao.int/author"),
        (CicdLabels.AUTHOR_ID, "cicd.skao.int/authorId"),
        (CicdLabels.BRANCH, "cicd.skao.int/branch"),
        (CicdLabels.COMMIT, "cicd.skao.int/commit"),
        (CicdLabels.ENV_TIER, "cicd.skao.int/environmentTier"),
        (CicdLabels.JOB, "cicd.skao.int/job"),
        (CicdLabels.JOB_ID, "cicd.skao.int/jobId"),
        (CicdLabels.MR_ID, "cicd.skao.int/mrId"),
        (CicdLabels.PERMITTED, "cicd.skao.int/permitted"),
        (CicdLabels.PIPELINE_ID, "cicd.skao.int/pipelineId"),
        (CicdLabels.PIPELINE_SOURCE, "cicd.skao.int/pipelineSource"),
        (CicdLabels.PROJECT, "cicd.skao.int/project"),
        (CicdLabels.PROJECT_ID, "cicd.skao.int/projectId"),
        (CicdLabels.PROJECT_PATH, "cicd.skao.int/projectPath"),
        (CicdLabels.TEAM, "cicd.skao.int/team"),
    ],
)
def test_cicd_labels_values(member, expected):
    assert str(member) == expected, "Enum value does not match expected string"


def test_namespace_status_superseded_value():
    """Superseded should be a first-class namespace status."""
    assert NamespaceStatus.SUPERSEDED.value == "superseded"
    assert NamespaceStatus.SUPERSEDED.value_numeric == 6
