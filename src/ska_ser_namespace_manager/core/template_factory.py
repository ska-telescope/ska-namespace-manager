"""
template_factory provides a jinja2 based template factory so that
it is simple to render a template anywhere on the code
"""

import hashlib
import os
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateError

from ska_ser_namespace_manager.core.logging import logging


def sha256(value: str, length: int = 64) -> str:
    """
    Compute sha256 hash
    :param value: Value to hash
    :param length: Length of the output hash
    :return: Hashed value with specified length
    """
    output_length = max(min(length, 64), 1)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:output_length]


class TemplateFactory:
    """
    TemplateFactory is a class responsible for loading
    templates and has helper methods
    """

    jinja_env: Environment

    def __init__(self, search_path: Optional[str] = None):
        self.jinja_env = Environment(
            loader=FileSystemLoader(
                searchpath=search_path
                or (
                    os.path.join(
                        os.path.dirname(os.path.realpath(__file__)),
                        "..",
                        "resources",
                        "templates",
                    )
                )
            )
        )
        self.jinja_env.filters["sha256"] = sha256

    def render(self, template: str, **kwargs) -> str | None:
        """
        Render a template with the specified arguments
        """
        try:
            return self.jinja_env.get_template(template).render(**kwargs)
        except TemplateError as exc:
            logging.error(
                "Failed to render template '%s' with arguments '%s': %s",
                template,
                kwargs,
                exc,
            )
            raise exc
