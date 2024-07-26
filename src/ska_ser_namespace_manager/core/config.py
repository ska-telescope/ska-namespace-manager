"""
config provides a basic configuration class meant to be
inherited by components specific classes
"""

import io
import logging
import os

import yaml

from ska_ser_namespace_manager.core.utils import Singleton

LOGGING_FORMAT = "%(asctime)s [level=%(levelname)s]: %(message)s"


class Config(metaclass=Singleton):
    """
    Config is a singleton class to provide abstraction from
    configuration loading

    config: Config data in dict form
    """

    config_data: dict

    def __init__(self, config: str | dict | io.IOBase = None) -> None:
        """
        Initializes base config properties

        :return:
        """
        super().__init__()
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        logging.basicConfig(
            level=logging.getLevelName(self.log_level), format=LOGGING_FORMAT
        )

        config_source = config
        if config_source is None:
            config_source = os.environ.get(
                "CONFIG_PATH", "/etc/config/config.yml"
            )

        if isinstance(config_source, str):
            logging.info("Loading configuration from %s", config_source)
            with open(config_source, encoding="utf-8") as cf:
                self.config_data = yaml.safe_load(cf)
        elif isinstance(config_source, io.IOBase):
            self.config_data = yaml.safe_load(config_source)
        else:
            self.config_data = config_source

        if self.config_data is None:
            self.config_data = {}
            logging.warning("Provided configuration is empty")

        self.load()

    def load(self) -> None:
        """
        Load configuration

        :return:
        """

    @classmethod
    def dispose(cls):
        """
        Dispose the instance of the class

        :param cls: class
        """
        if cls in cls._instances:
            del cls._instances[cls]
