"""test_ownership_collector tests ownership collection behavior"""

from unittest.mock import MagicMock, patch

from ska_ser_namespace_manager.collector.ownership_collector import (
    OwnershipCollector,
)
from ska_ser_namespace_manager.core.types import NamespaceAnnotations


def make_collector() -> OwnershipCollector:
    collector = OwnershipCollector.__new__(OwnershipCollector)
    collector.namespace = "ci-test"
    collector.config = MagicMock()
    collector.config.people_api.url = "http://people-api"
    collector.config.people_api.ca = None
    collector.config.people_api.ca_path = None
    collector.config.people_api.insecure = True
    return collector


def test_get_owner_info_returns_when_namespace_missing():
    collector = make_collector()
    collector.get_namespace = MagicMock(return_value=None)

    collector.get_owner_info()

    collector.get_namespace.assert_called_once_with("ci-test")


def test_get_owner_info_patches_owner_annotation():
    collector = make_collector()
    namespace = MagicMock()
    namespace.metadata.labels = {"cicd.skao.int/author": "pedro"}
    namespace.metadata.annotations = {
        "cicd.skao.int/authorEmail": "pedro@example.com"
    }
    collector.get_namespace = MagicMock(return_value=namespace)
    collector.patch_namespace = MagicMock()

    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"name": "Pedro", "slack_id": "U123"}

    user = MagicMock()
    user.name = "Pedro"
    user.slack_id = "U123"

    with patch(
        "ska_ser_namespace_manager.collector.ownership_collector.requests.get",
        return_value=response,
    ) as mock_get, patch(
        "ska_ser_namespace_manager.collector.ownership_collector.PeopleDatabaseUser",
        return_value=user,
    ), patch(
        "ska_ser_namespace_manager.collector.ownership_collector.encode_slack_address",
        return_value="Pedro[U123]",
    ):
        collector.get_owner_info()

    mock_get.assert_called_once()
    collector.patch_namespace.assert_called_once_with(
        "ci-test",
        annotations={NamespaceAnnotations.OWNER.value: "Pedro[U123]"},
    )


def test_get_owner_info_exits_on_not_found():
    collector = make_collector()
    namespace = MagicMock()
    namespace.metadata.labels = {}
    namespace.metadata.annotations = {}
    collector.get_namespace = MagicMock(return_value=namespace)

    response = MagicMock()
    response.status_code = 404

    with patch(
        "ska_ser_namespace_manager.collector.ownership_collector.requests.get",
        return_value=response,
    ), patch(
        "ska_ser_namespace_manager.collector.ownership_collector.sys.exit"
    ) as mock_exit:
        collector.get_owner_info()

    mock_exit.assert_called_once_with(0)
