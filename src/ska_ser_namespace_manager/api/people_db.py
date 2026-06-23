"""
people_db wraps in a singleton class the PeopleDatabaseAPI
from ska_cicd_services_api
"""

from ska_cicd_services_api.people_database_api import PeopleDatabaseApi

from ska_ser_namespace_manager.api.api_config import (
    APIConfig,
    PeopleDatabaseConfig,
)
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.utils import Singleton


class PeopleDB(metaclass=Singleton):  # pragma: no cover
    """
    PeopleDB wraps PeopleDatabaseApi in a singleton class
    """

    api: PeopleDatabaseApi | None
    config: PeopleDatabaseConfig

    def __init__(self) -> None:
        """
        Initializes people database singleton wrapper
        """
        config: APIConfig = ConfigLoader().load(APIConfig)
        self.config = config.people_database
        self.api = None
        if not self.config.enabled:
            return

        self.api = PeopleDatabaseApi(
            service_account_data=self.config.credentials.model_dump(),
            spreadsheet_id=self.config.spreadsheet_id,
            spreadsheet_range=self.config.spreadsheet_range,
            cache_ttl=self.config.cache_ttl,
        )

    async def refresh(self) -> bool:
        """
        Refresh the cache
        """
        if not self.api:
            return True

        await self.api._get_sheet()
        return self.api._cache_available()
