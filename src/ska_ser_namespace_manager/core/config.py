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

_YAML_SUFFIXES = (".yml", ".yaml")


def _deep_merge(base: dict, overlay: dict) -> dict:
    """
    Recursively merge ``overlay`` into ``base``. Overlay values win for
    scalars and lists; nested dicts are merged key-by-key. An overlay value of
    ``None`` is treated as "leave the base value alone" so that blank entries
    in a layered file do not erase values supplied by another layer.
    """
    result = dict(base)
    for key, overlay_value in overlay.items():
        if overlay_value is None:
            continue
        base_value = result.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            result[key] = _deep_merge(base_value, overlay_value)
        else:
            result[key] = overlay_value
    return result


def _load_yaml_directory(directory: str) -> dict | None:
    """
    Load all ``*.yml`` / ``*.yaml`` files from ``directory`` (skipping hidden
    entries), sorted alphabetically, and deep-merge them into a single dict.
    Returns ``None`` if the directory contains no eligible files.
    """
    entries = sorted(
        name
        for name in os.listdir(directory)
        if not name.startswith(".") and name.endswith(_YAML_SUFFIXES)
    )
    if not entries:
        return None

    merged: dict = {}
    for name in entries:
        path = os.path.join(directory, name)
        with open(path, encoding="utf-8") as cf:
            data = yaml.safe_load(cf) or {}
        if not isinstance(data, dict):
            raise ValueError(
                f"Config file {path} must contain a YAML mapping at the top "
                f"level, got {type(data).__name__}"
            )
        merged = _deep_merge(merged, data)
    return merged


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
        :param config: Config data or source. When a string is provided (or
            ``CONFIG_PATH`` resolves to one) it may point at a single YAML
            file or at a directory of layered YAML files merged
            alphabetically (later filenames override earlier ones).
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
            source_kind = "directory" if os.path.isdir(config_path) else "file"
            logging.info(
                "Loading configuration for '%s' from %s (%s)",
                clazz.__qualname__,
                config_path,
                source_kind,
            )
            try:
                if source_kind == "directory":
                    config_data = _load_yaml_directory(config_path)
                    if config_data is None:
                        logging.warning(
                            "No YAML files found in config directory %s. "
                            "Loading default config.",
                            config_path,
                        )
                        return clazz()
                else:
                    with open(config_path, encoding="utf-8") as cf:
                        config_data = yaml.safe_load(cf)
            except Exception:  # pylint: disable=broad-exception-caught
                logging.warning(
                    "Failed to load config from %s. Loading default config.",
                    source_kind,
                )
                return clazz()
        elif isinstance(config_source, io.IOBase):
            config_data = yaml.safe_load(config_source)

        if config_data is None:
            raise ValueError("Unable to load a valid configuration")

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
