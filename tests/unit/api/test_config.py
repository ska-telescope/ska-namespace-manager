"""test_config tests the APIConfig class"""

import pytest

from ska_ser_namespace_manager.api.api_config import APIConfig
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
