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


class ConfigLoader(metaclass=Singleton):
    """
    ConfigLoader is a singleton class responsible for loading
    configurations only once
    """

    configs: dict

    def __init__(self):
        super().__init__()
        self.configs = defaultdict()

    def load(self, clazz: T, config: str | dict | io.IOBase = None) -> T:
        """
        Loads a configuration and stores it in a "singleton"
        list.

        :param clazz: Class of the configuration
        :param config: Config data or source.
        """
        if clazz in self.configs:
            return self.configs[clazz]

        config_source = config
        if config_source is None:
            config_source = os.environ.get(
                "CONFIG_PATH", "/etc/config/config.yml"
            )
        config_data = config
        if config is None or isinstance(config_source, str):
            config_path = (
                config
                if config
                else os.environ.get("CONFIG_PATH", "/etc/config/config.yml")
            )
            logging.info(
                "Loading configuration for '%s' from %s",
                clazz.__qualname__,
                config_path,
            )
            try:
                with open(config_path, encoding="utf-8") as cf:
                    config_data = yaml.safe_load(cf)
            except Exception:  # pylint: disable=broad-exception-caught
                logging.warning(
                    "Failed to load config from file. Loading default config."
                )
                return clazz()
        elif isinstance(config_source, io.IOBase):
            config_data = yaml.safe_load(config_source)

        if config_data is None:
            raise ValueError("Unable to load a valid configuration")

        # Debug output to check what is being loaded
        logging.debug(f"Loaded config data: {config_data}")

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
