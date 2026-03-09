"""
config provides a basic configuration classes meant to be
inherited by components specific classes and a singleton
configuration loader
"""

import io
import os
from collections import defaultdict
from typing import TypeVar

import yaml
from pydantic import BaseModel

from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.utils import Singleton

T = TypeVar("T", bound=BaseModel)


def summarize_config_data(config_data: dict) -> dict:
    """
    Return a redacted summary of loaded config keys.
    """
    if not isinstance(config_data, dict):
        return {"type": type(config_data).__name__}

    return {
        "keys": sorted(config_data.keys()),
        "top_level_types": {
            key: type(value).__name__ for key, value in config_data.items()
        },
    }


class ConfigLoader(metaclass=Singleton):
    """
    ConfigLoader is a singleton class responsible for loading
    configurations only once
    """

    configs: dict

    def __init__(self):
        super().__init__()
        self.configs = defaultdict()

    def _get_default_config_path(self) -> str:
        """
        Return the default config path.
        """
        return os.environ.get("CONFIG_PATH", "/etc/config/config.yml")

    def _load_config_from_path(self, config_path: str):
        """
        Load config data from a file path.
        """
        with open(config_path, encoding="utf-8") as cf:
            return yaml.safe_load(cf)

    def _load_config_data(self, clazz: T, config: str | dict | io.IOBase = None):
        """
        Resolve config data from the supported config sources.
        """
        config_source = config if config is not None else self._get_default_config_path()
        if isinstance(config_source, dict):
            return config_source

        if isinstance(config_source, io.IOBase):
            return yaml.safe_load(config_source)

        config_path = config_source
        logging.info(
            "Loading configuration for '%s' from %s",
            clazz.__qualname__,
            config_path,
        )
        return self._load_config_from_path(config_path)

    def load(self, clazz: T, config: str | dict | io.IOBase = None) -> T:
        """
        Loads a configuration and stores it in a "singleton"
        list.

        :param clazz: Class of the configuration
        :param config: Config data or source.
        """
        if clazz in self.configs:
            return self.configs[clazz]

        try:
            config_data = self._load_config_data(clazz, config)
        except Exception:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Failed to load config from file. Loading default config."
            )
            return clazz()

        if config_data is None:
            raise ValueError("Unable to load a valid configuration")

        logging.debug(
            "Loaded config summary for '%s': %s",
            clazz.__qualname__,
            summarize_config_data(config_data),
        )

        # Initialize the configuration class
        self.configs[clazz] = clazz(**config_data)
        return self.configs[clazz]

    def dispose(self, clazz: type) -> None:
        """
        Removes the loaded class from the "singleton" instances

        :param clazz: Class of the configuration
        """
        if clazz in self.configs:
            del self.configs[clazz]
