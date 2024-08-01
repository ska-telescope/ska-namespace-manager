"""
template_factory provides a jinja2 based template factory so that
it is simple to render a template anywhere on the code
"""

import os

from jinja2 import Environment, FileSystemLoader, TemplateError

from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.utils import Singleton


class TemplateFactory(metaclass=Singleton):
    """
    TemplateFactory is a singleton class responsible for loading
    templates
    """

    jinja_env: Environment

    def __init__(self):
        super().__init__()
        self.jinja_env = Environment(
            loader=FileSystemLoader(
                searchpath=os.path.join(
                    os.path.dirname(os.path.realpath(__file__)),
                    "..",
                    "resources",
                    "templates",
                )
            )
        )
        # Add custom jinja filters by
        # self.jinja_env.filters["<filter name>"] = <filter function>

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
