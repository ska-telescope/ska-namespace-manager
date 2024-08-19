from unittest.mock import MagicMock, patch

from ska_ser_namespace_manager.core.notifier import Notifier
from ska_ser_namespace_manager.core.utils import encode_slack_address


def test_notify_user_success():
    with patch(
        "ska_ser_namespace_manager.core.notifier.TemplateFactory"
    ) as mock_template_factory, patch(
        "ska_ser_namespace_manager.core.notifier.App", autospec=True
    ) as mock_app:
        # Setup mock return values
        mock_template_factory.return_value.render.return_value = (
            "Mocked Message"
        )
        mock_app.return_value.client.chat_postMessage = MagicMock()
        notifier = Notifier(slack_token="fake_slack_token")
        success = notifier.notify_user(
            encode_slack_address("marvin", "marvin"), "template_name", "status"
        )

        assert success
        mock_app.return_value.client.chat_postMessage.assert_called_once()


def test_notify_user_no_slack_token():
    with patch(
        "ska_ser_namespace_manager.core.template_factory.TemplateFactory"
    ):
        # Instantiate the Notifier with no Slack token
        notifier = Notifier(slack_token=None)
        success = notifier.notify_user(
            "encoded_address", "template_name", "status"
        )
        assert success is False


def test_notify_user_failure():
    with patch(
        "ska_ser_namespace_manager.core.notifier.TemplateFactory"
    ) as mock_template_factory, patch(
        "ska_ser_namespace_manager.core.notifier.App", autospec=True
    ) as mock_app:
        # Setup mock return values
        mock_template_factory.return_value.render.return_value = (
            "Mocked Message"
        )
        mock_app.return_value.client.chat_postMessage = MagicMock()
        notifier = Notifier(slack_token="fake_slack_token")
        assert not notifier.notify_user(
            encode_slack_address("marvin", ""), "template_name", "status"
        )
        assert not notifier.notify_user("", "template_name", "status")
        assert not notifier.notify_user(None, "template_name", "status")

        mock_app.return_value.client.chat_postMessage.assert_not_called()


def test_notify_user_slack_exception():
    with patch(
        "ska_ser_namespace_manager.core.notifier.TemplateFactory"
    ) as mock_template_factory, patch(
        "ska_ser_namespace_manager.core.notifier.App", autospec=True
    ) as mock_app:
        # Setup mock return values
        mock_template_factory.return_value.render.return_value = (
            "Mocked Message"
        )
        mock_app.return_value.client.chat_postMessage.side_effect = Exception(
            "Failed to fetch pods"
        )
        notifier = Notifier(slack_token="fake_slack_token")
        assert not notifier.notify_user(
            encode_slack_address("marvin", "marvin"), "template_name", "status"
        )

        mock_app.return_value.client.chat_postMessage.assert_called()


def test_marvin_quote():
    with patch(
        "ska_ser_namespace_manager.core.notifier.TemplateFactory"
    ), patch("ska_ser_namespace_manager.core.notifier.App", autospec=True):
        notifier = Notifier(slack_token="fake_slack_token")
        assert len(notifier.get_marvin_quote("failing")) > 0
        assert len(notifier.get_marvin_quote(None)) > 0
