import pytest

from ska_ser_namespace_manager.core.types import NamespaceAnnotations


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
        (NamespaceAnnotations.OWNER, "manager.cicd.skao.int/owner"),
        (
            NamespaceAnnotations.FAILING_RESOURCES,
            "manager.cicd.skao.int/failing_resources",
        ),
        (
            NamespaceAnnotations.NOTIFIED_TS,
            "manager.cicd.skao.int/notified_timestamp",
        ),
    ],
)
def test_namespace_annotations_values(member, expected):
    assert str(member) == expected, "Enum value does not match expected string"
