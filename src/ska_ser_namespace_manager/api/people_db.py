"""
people_db wraps in a singleton class the PeopleDatabaseAPI
from ska_cicd_services_api
"""

from ska_cicd_services_api.people_database_api import PeopleDatabaseApi

from ska_ser_namespace_manager.api.api_config import APIConfig
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.utils import Singleton


class PeopleDB(PeopleDatabaseApi, metaclass=Singleton):  # pragma: no cover
    """
    PeopleDB wraps PeopleDatabaseApi in a singleton class
    """

    def __init__(self) -> None:
        """
        Initializes people database singleton wrapper

        :return:
        """
        config: APIConfig
        config = ConfigLoader().load(APIConfig)
        people_db_config = config.people_database
        PeopleDatabaseApi.__init__(
            self,
            service_account_data=people_db_config.credentials.model_dump(),
            spreadsheet_id=people_db_config.spreadsheet_id,
            spreadsheet_range=people_db_config.spreadsheet_range,
            cache_ttl=people_db_config.cache_ttl,
        )

    async def refresh(self) -> bool:
        """
        Refresh the cache
        :return: True if cache is present, False otherwise
        """

        await self._get_sheet()
        return self._cache_available()
