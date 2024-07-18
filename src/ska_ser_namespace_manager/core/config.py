"""
config provides a basic configuration class meant to be
inherited by components specific classes
"""

import logging
import os

from ska_ser_namespace_manager.core.utils import Singleton

LOGGING_FORMAT = "%(asctime)s [level=%(levelname)s]: %(message)s"


class Config(metaclass=Singleton):
    """
    Config is a singleton class to provide abstraction from
    configuration loading
    """

    config_path: str

    def __init__(self) -> None:
        """
        Initializes base config properties

        :return:
        """
        super().__init__()
        self.config_path = os.environ.get(
            "CONFIG_PATH", "/etc/config/config.yml"
        )
        self.log_level = os.environ.get("LOG_LEVEL", "INFO")
        logging.basicConfig(
            level=logging.getLevelName(self.log_level), format=LOGGING_FORMAT
        )
        self.load()
        logging.info("Loaded configuration from %s", self.config_path)

    def load(self) -> None:
        """
        Load configuration from self.config_path

        :return:
        """
