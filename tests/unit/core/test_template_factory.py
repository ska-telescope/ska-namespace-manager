import os
import tempfile
from unittest.mock import patch

import pytest
from jinja2 import TemplateError

from ska_ser_namespace_manager.core.template_factory import TemplateFactory


def test_template_factory_initialization_default_path():
    with patch("os.path.join") as mock_join:
        mock_join.return_value = "/fake/path"
        factory = TemplateFactory()
        assert factory.jinja_env.loader.searchpath == ["/fake/path"]


def test_template_factory_initialization_custom_path():
    custom_path = "/custom/templates"
    factory = TemplateFactory(search_path=custom_path)
    assert factory.jinja_env.loader.searchpath == [custom_path]


@pytest.fixture()
def templates_custom_path():
    with tempfile.TemporaryDirectory() as tpldir:
        with open(
            os.path.join(tpldir, "template.j2"),
            encoding="utf-8",
            mode="w+",
        ) as tf:
            tf.write("Hello, {{ name }}!")

        yield tpldir


class TestTemplates:
    def test_render_template_success(self, templates_custom_path):
        factory = TemplateFactory(templates_custom_path)
        assert factory.render("template.j2", name="World") == "Hello, World!"
        assert factory.render("template.j2") == "Hello, !"

    def test_render_template_failure(self, templates_custom_path):
        factory = TemplateFactory(templates_custom_path)
        with pytest.raises(TemplateError):
            factory.render("nonexistent.txt")
