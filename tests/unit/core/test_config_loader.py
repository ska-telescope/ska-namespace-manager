"""test_config_loader tests the ConfigLoader class"""

import io
import json
import os
import tempfile

import pytest
from pydantic import BaseModel

from ska_ser_namespace_manager.core.config import ConfigLoader


class SomeConfig(BaseModel):
    """
    SomeConfig test class
    """

    int_field: int = 1
    string_field: str


@pytest.fixture()
def config_from_path():
    config_path: str
    with tempfile.NamedTemporaryFile(delete=False) as fp:
        fp.write(
            json.dumps(
                {
                    "string_field": "config_from_path",
                }
            ).encode("utf-8")
        )
        config_path = fp.name

    yield config_path
    ConfigLoader().dispose(SomeConfig)


@pytest.fixture()
def config_from_dict():
    yield {
        "int_field": 2,
        "string_field": "config_from_dict",
    }
    ConfigLoader().dispose(SomeConfig)


@pytest.fixture()
def config_from_stream():
    yield io.StringIO(
        json.dumps(
            {
                "int_field": 3,
                "string_field": "config_from_stream",
            }
        )
    )
    ConfigLoader().dispose(SomeConfig)


class TestConfigLoader:
    def test_dispose(self):
        config: SomeConfig
        config = ConfigLoader().load(SomeConfig, {"string_field": "before"})

        assert config.string_field == "before"

        ConfigLoader().dispose(SomeConfig)

        config: SomeConfig
        config = ConfigLoader().load(SomeConfig, {"string_field": "after"})

        assert config.string_field == "after"

        ConfigLoader().dispose(SomeConfig)

    def test_load_config_from_envvar_path(self, config_from_path):
        os.environ["CONFIG_PATH"] = config_from_path
        config: SomeConfig
        config = ConfigLoader().load(SomeConfig)

        assert config.int_field == 1
        assert config.string_field == "config_from_path"

        del os.environ["CONFIG_PATH"]

    def test_load_config_from_path(self, config_from_path):
        config: SomeConfig
        config = ConfigLoader().load(SomeConfig, config_from_path)

        assert config.int_field == 1
        assert config.string_field == "config_from_path"

    def test_load_config_from_dict(self, config_from_dict):
        config: SomeConfig
        config = ConfigLoader().load(SomeConfig, config_from_dict)

        assert config.int_field == 2
        assert config.string_field == "config_from_dict"

    def test_load_config_from_stream(self, config_from_stream):
        config: SomeConfig
        config = ConfigLoader().load(SomeConfig, config_from_stream)

        assert config.int_field == 3
        assert config.string_field == "config_from_stream"
