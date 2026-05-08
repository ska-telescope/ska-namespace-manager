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


def test_cancelled_namespace_templates_render():
    """Cancelled namespace notifications should render."""
    factory = TemplateFactory()

    status_message = factory.render(
        "cancelled-namespace-notification.j2",
        user="marvin",
        target_namespace="ci-test",
        status="cancelled",
        job_url="https://gitlab.example/job",
        quote="Life.",
    )
    delete_message = factory.render(
        "namespace-deleted-notification.j2",
        user="marvin",
        target_namespace="ci-test",
        status="cancelled",
        job_url="https://gitlab.example/job",
        quote="Life.",
    )

    assert "ci-test" in status_message
    assert "manually deleted, or cancelled" in status_message
    assert "manually deleted or cancelled" in delete_message


def test_superseded_namespace_templates_render():
    """Superseded namespace notifications should render."""
    factory = TemplateFactory()

    status_message = factory.render(
        "superseded-namespace-notification.j2",
        user="marvin",
        target_namespace="ci-test",
        status="superseded",
        job_url="https://gitlab.example/job",
        quote="Life.",
    )
    delete_message = factory.render(
        "namespace-deleted-notification.j2",
        user="marvin",
        target_namespace="ci-test",
        status="superseded",
        job_url="https://gitlab.example/job",
        quote="Life.",
    )

    assert "ci-test" in status_message
    assert "newer deployment" in status_message
    assert "newer deployment" in delete_message


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
