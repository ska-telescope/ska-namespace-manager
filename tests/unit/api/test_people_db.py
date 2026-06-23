"""test_people_db tests the people database wrapper."""

from unittest.mock import AsyncMock, patch

import pytest

from ska_ser_namespace_manager.api.api_config import (
    APIConfig,
    GoogleServiceAccount,
    PeopleDatabaseConfig,
)
from ska_ser_namespace_manager.api.people_db import PeopleDB
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.utils import Singleton

dummy_credentials = GoogleServiceAccount(
    project_id="dummy",
    private_key_id="dummy",
    private_key="dummy",
    client_email="dummy",
    client_id="dummy",
    client_x509_cert_url="dummy",
)


@pytest.fixture(autouse=True)
def reset_singletons():
    """
    Resets singleton instances between tests.
    """
    Singleton._instances.pop(PeopleDB, None)
    Singleton._instances.pop(ConfigLoader, None)
    yield
    Singleton._instances.pop(PeopleDB, None)
    Singleton._instances.pop(ConfigLoader, None)


@pytest.mark.asyncio
async def test_disabled_people_db_does_not_create_api():
    """
    Disabled PeopleDB instances do not create an API client.
    """
    config_loader = ConfigLoader()
    config_loader.configs[APIConfig] = APIConfig(
        people_database=PeopleDatabaseConfig(enabled=False)
    )

    people_db = PeopleDB()

    assert people_db.api is None
    assert await people_db.refresh() is True


@pytest.mark.asyncio
async def test_enabled_people_db_delegates_to_embedded_api():
    """
    Enabled PeopleDB instances delegate calls to the embedded API client.
    """
    config_loader = ConfigLoader()
    config_loader.configs[APIConfig] = APIConfig(
        people_database=PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy-sheet",
        )
    )

    with patch(
        "ska_ser_namespace_manager.api.people_db.PeopleDatabaseApi"
    ) as mock_api_class:
        api = mock_api_class.return_value
        api._get_sheet = AsyncMock()
        api._cache_available.return_value = True

        people_db = PeopleDB()

        assert people_db.api is api
        mock_api_class.assert_called_once_with(
            service_account_data=dummy_credentials.model_dump(),
            spreadsheet_id="dummy-sheet",
            spreadsheet_range="System Team API!A2:Z1001",
            cache_ttl=3600,
        )
        assert await people_db.refresh() is True
        api._get_sheet.assert_awaited_once_with()
        api._cache_available.assert_called_once_with()
