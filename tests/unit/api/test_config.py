"""test_config tests the APIConfig class"""

import pytest

from ska_ser_namespace_manager.api.api_config import (
    APIConfig,
    PeopleDatabaseConfig,
)
from ska_ser_namespace_manager.core.config import ConfigLoader


@pytest.fixture()
def config_https_enabled():
    ConfigLoader().dispose(APIConfig)
    yield {
        "https_enabled": True,
        "pki_path": "https-enabled",
        "people_database": {
            "credentials": {
                "client_email": "dummy",
                "client_id": "dummy",
                "client_x509_cert_url": "dummy",
                "private_key": "dummy",
                "private_key_id": "dummy",
                "project_id": "dummy",
            },
            "spreadsheet_id": "dummy",
        },
    }


@pytest.fixture()
def config_https_disabled():
    ConfigLoader().dispose(APIConfig)
    yield {
        "https_enabled": False,
        "pki_path": "https-disabled",
        "people_database": {
            "credentials": {
                "client_email": "dummy",
                "client_id": "dummy",
                "client_x509_cert_url": "dummy",
                "private_key": "dummy",
                "private_key_id": "dummy",
                "project_id": "dummy",
            },
            "spreadsheet_id": "dummy",
        },
    }


class TestAPIConfig:
    def test_config_https_enabled(self, config_https_enabled):
        config: APIConfig
        config = ConfigLoader().load(APIConfig, config_https_enabled)
        assert config.https_enabled
        assert config.pki_path == "https-enabled"
        assert config.ca_path == "https-enabled/ca.crt"
        assert config.cert_path == "https-enabled/tls.crt"
        assert config.key_path == "https-enabled/tls.key"

    def test_config_https_disabled(self, config_https_disabled):
        config: APIConfig
        config = ConfigLoader().load(APIConfig, config_https_disabled)

        assert not config.https_enabled
        assert config.pki_path == "https-disabled"
        assert not config.ca_path
        assert not config.cert_path
        assert not config.key_path


class TestPeopleDatabaseConfig:
    def test_disabled_without_credentials(self):
        config = PeopleDatabaseConfig(enabled=False)
        assert not config.enabled
        assert config.credentials is None
        assert config.spreadsheet_id is None

    def test_default_people_database_config_requires_enabled_fields(self):
        with pytest.raises(ValueError):
            PeopleDatabaseConfig()

    def test_people_database_defaults_to_disabled(self):
        ConfigLoader().dispose(APIConfig)
        config = ConfigLoader().load(APIConfig, {"https_enabled": False})
        assert config.people_database is not None
        assert not config.people_database.enabled

    def test_enabled_without_credentials_raises(self):
        with pytest.raises(ValueError):
            PeopleDatabaseConfig(enabled=True, spreadsheet_id="dummy")

    def test_enabled_without_spreadsheet_id_raises(self):
        with pytest.raises(ValueError):
            PeopleDatabaseConfig(
                enabled=True,
                credentials={
                    "project_id": "dummy",
                    "private_key": "dummy",
                    "client_email": "dummy",
                },
            )

    def test_empty_people_database_mapping_defaults_to_disabled(self):
        config = ConfigLoader().load(
            APIConfig,
            {"https_enabled": False, "people_database": {}},
        )

        assert not config.people_database.enabled
        assert config.people_database.credentials is None
        assert config.people_database.spreadsheet_id is None
