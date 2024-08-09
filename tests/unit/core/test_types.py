import pytest

from ska_ser_namespace_manager.core.types import (
    CicdAnnotations,
    NamespaceAnnotations,
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
            NamespaceAnnotations.STATUS_DETAIL,
            "manager.cicd.skao.int/status_detail",
        ),
        (
            NamespaceAnnotations.STATUS_FINALIZE_AT,
            "manager.cicd.skao.int/status_finalize_at",
        ),
        (NamespaceAnnotations.OWNER, "manager.cicd.skao.int/owner"),
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
    [(CicdAnnotations.JOB_URL, "cicd.skao.int/jobUrl")],
)
def test_cicd_annotations_values(member, expected):
    assert str(member) == expected, "Enum value does not match expected string"
