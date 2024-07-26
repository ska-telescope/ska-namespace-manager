"""test_config tests the APIConfig class"""

import io
import json
import os
import tempfile

import pytest

from ska_ser_namespace_manager.api.api_config import APIConfig
from ska_ser_namespace_manager.core.config import Config


@pytest.fixture()
def config_from_path():
    config_path: str
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        fp.write(
            json.dumps(
                {
                    "httpsEnabled": True,
                    "pkiPath": "file-path",
                    "people_db": {
                        "credentials": {
                            "client_email": "dummy",
                            "client_id": "dummy",
                            "client_x509_cert_url": "dummy",
                            "private_key": "dummy",
                            "private_key_id": "dummy",
                            "project_id": "dummy",
                        },
                        "spreadsheet_id": "file-dummy",
                    },
                }
            ).encode("utf-8")
        )
        config_path = fp.name

    yield config_path
    APIConfig.dispose()


@pytest.fixture()
def config_from_dict():
    yield {
        "httpsEnabled": True,
        "pkiPath": "dict-path",
        "people_db": {
            "credentials": {
                "client_email": "dummy",
                "client_id": "dummy",
                "client_x509_cert_url": "dummy",
                "private_key": "dummy",
                "private_key_id": "dummy",
                "project_id": "dummy",
            },
            "spreadsheet_id": "dict-dummy",
        },
    }
    APIConfig.dispose()


@pytest.fixture()
def config_from_stream():
    yield io.StringIO(
        json.dumps(
            {
                "pkiPath": "stream-path",
                "people_db": {
                    "credentials": {
                        "client_email": "dummy",
                        "client_id": "dummy",
                        "client_x509_cert_url": "dummy",
                        "private_key": "dummy",
                        "private_key_id": "dummy",
                        "project_id": "dummy",
                    },
                    "spreadsheet_id": "stream-dummy",
                },
            }
        )
    )
    APIConfig.dispose()


def test_config_dispose():
    os.environ["LOG_LEVEL"] = "DEBUG"
    config = Config("/dev/null")
    assert config.log_level == os.environ["LOG_LEVEL"]

    Config.dispose()

    os.environ["LOG_LEVEL"] = "INFO"
    config = Config("/dev/null")
    assert config.log_level == os.environ["LOG_LEVEL"]


class TestConfig:
    def test_load_config_from_envvar_path(self, config_from_path):
        os.environ["CONFIG_PATH"] = config_from_path
        APIConfig()
        del os.environ["CONFIG_PATH"]

    def test_load_config_from_path(self, config_from_path):
        config = APIConfig(config_from_path)
        assert config.https_port == 9443
        assert config.https_enabled
        assert config.pki_path == "file-path"
        assert config.http_port == 8080
        assert config.ca_path == "file-path/ca.crt"
        assert config.cert_path == "file-path/tls.crt"
        assert config.key_path == "file-path/tls.key"
        assert config.people_database.spreadsheet_id == "file-dummy"
        assert config.people_database.cache_ttl == 3600

    def test_load_config_from_dict(self, config_from_dict):
        config = APIConfig(config_from_dict)
        assert config.ca_path == "dict-path/ca.crt"
        assert config.cert_path == "dict-path/tls.crt"
        assert config.key_path == "dict-path/tls.key"
        assert config.people_database.spreadsheet_id == "dict-dummy"

    def test_load_config_from_stream(self, config_from_stream):
        config = APIConfig(config_from_stream)
        assert not config.https_enabled
        assert not config.ca_path
        assert config.people_database.spreadsheet_id == "stream-dummy"
