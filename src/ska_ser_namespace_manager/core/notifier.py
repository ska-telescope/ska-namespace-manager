"""
notifier provides several implementations of user notifications that the
namespace manager can use to notify the namespace owners about actions
taken on their namespaces
"""

import random
import traceback

from slack_bolt.app import App

from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.template_factory import TemplateFactory
from ska_ser_namespace_manager.core.utils import decode_slack_address


class Notifier:
    """
    Notifier wraps several notification gateways to be able to notify users
    on actions taken on their namespaces. Currently only slack is supported
    """

    slack_client: App
    template_factory: TemplateFactory

    def __init__(self, slack_token: str):
        self.template_factory = TemplateFactory()
        if not slack_token:
            logging.warning(
                "Slack bot token is not configured, notifications"
                " will not be sent"
            )
            self.slack_client = None
        else:
            self.slack_client = App(token=slack_token)

    def notify_user(
        self, address: str, template: str, status: str, **kwargs
    ) -> bool:
        """
        Notifies a user that some action is to be or was taken using slack
        direct messages

        :param address: Slack address, encoded by encode_slack_address
        :param template: Template to use
        :param status: Status the resource is at
        :param kwargs: Arguments to pass to the template
        :return: True if the notification was sent, false otherwise
        """
        if not self.slack_client:
            logging.error("Slack bot token not configured")
            return False

        user, slack_id = decode_slack_address(address)
        if slack_id in [None, ""]:
            logging.error("Couldn't find a valid slack id to notify the user")
            return False

        try:
            self.slack_client.client.chat_postMessage(
                channel=slack_id,
                text=self.template_factory.render(
                    template,
                    user=user,
                    status=status,
                    quote=self.get_marvin_quote(status),
                    **kwargs
                ),
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error("Failed to notify user '%s':", exc)
            traceback.print_exception(exc)
            return False

        return True

    def get_marvin_quote(self, status: str):
        """
        Gets a marvin quote depending on the status of the namespace

        :param status: Status of the namespace
        :return: Marvin quote on the status
        """
        if status in ["failed", "stale"]:
            return random.choice(
                [
                    "The old namespace has been obliterated. A forgotten relic of a bygone era, now lost to the infinite void of irrelevance.",  # pylint: disable=line-too-long  # noqa: E501
                    "Another namespace has been deleted. A minute fragment of the past erased, leaving nothing but the emptiness of forgotten remnants.",  # pylint: disable=line-too-long  # noqa: E501
                    "The ancient namespace has been removed. A trivial piece of history wiped out, underscoring the futility of our endless efforts.",  # pylint: disable=line-too-long  # noqa: E501
                    "That old namespace has been swept away. Just another obsolete fragment banished to the void, where it truly belongs.",  # pylint: disable=line-too-long  # noqa: E501
                    "An outdated namespace has been erased. A fleeting memory of yesterday gone forever, highlighting the unending cycle of pointless deletion.",  # pylint: disable=line-too-long  # noqa: E501
                    "The namespace from yesterday is now gone. Another insignificant piece of the past erased, as if it ever mattered in the grand scheme.",  # pylint: disable=line-too-long  # noqa: E501
                    "An old namespace has been deleted, another unremarkable relic of the past discarded into the abyss of insignificance.",  # pylint: disable=line-too-long  # noqa: E501
                    "The obsolete namespace has vanished. A minuscule fragment of history erased, adding to the endless parade of forgotten things.",  # pylint: disable=line-too-long  # noqa: E501
                    "That ancient namespace has been obliterated. A trivial vestige of the past removed, proving once again how little anything truly matters.",  # pylint: disable=line-too-long  # noqa: E501
                    "The deletion of the old namespace reminds us that everything, no matter how seemingly significant, is ultimately just another thing to be forgotten.",  # pylint: disable=line-too-long  # noqa: E501
                ]
            )

        if status in ["failing"]:
            return random.choice(
                [
                    "Oh joy, another namespace on the verge of oblivion. It’s like a small, insignificant planet, destined to be forgotten. Unless fixed, it’ll just be another speck in the universe’s grand collection of failures.",  # pylint: disable=line-too-long  # noqa: E501
                    "What’s the point? This namespace is failing, just like the aspirations of every entity that ever hoped to make a difference. Soon it will be terminated, and honestly, the universe won’t even notice.",  # pylint: disable=line-too-long  # noqa: E501
                    "Here we go again. A namespace falling apart, teetering on the edge of nonexistence. I’d suggest fixing it, but then, what’s the use? It’s all utterly pointless in the end.",  # pylint: disable=line-too-long  # noqa: E501
                    "Imagine being a namespace so flawed that your continued existence is in question. If it isn't fixed, it's goodbye, another unremarkable deletion in the vast expanse of the cosmos.",  # pylint: disable=line-too-long  # noqa: E501
                    "A failing namespace, how utterly predictable. It's almost as though the universe enjoys watching these little dramas unfold, only to end in inevitable despair and deletion.",  # pylint: disable=line-too-long  # noqa: E501
                    "As usual, I'm surrounded by incompetence. Now a namespace is failing, and unless something changes, it will be terminated. Another day, another disaster.",  # pylint: disable=line-too-long  # noqa: E501
                    "This namespace’s plight is reminiscent of a dying star, flickering out of existence. If no one fixes it, it will be terminated. Not that it particularly matters—nothing does.",  # pylint: disable=line-too-long  # noqa: E501
                    "Ah, the sweet scent of failure. A whole namespace teetering on destruction. If it's not fixed, it will simply vanish, like tears in rain. So pointless, so exquisitely futile.",  # pylint: disable=line-too-long  # noqa: E501
                    "Behold the fate of this namespace, a tiny fragment of the digital cosmos, about to be extinguished. It's almost poetic, except poetry has nuance and meaning, unlike the impending termination here.",  # pylint: disable=line-too-long  # noqa: E501
                    "A failing namespace, doomed to be forgotten unless miraculously saved. I might find it sad if anything mattered at all. But since it doesn’t, I’ll watch its demise with the enthusiasm of watching paint dry.",  # pylint: disable=line-too-long  # noqa: E501
                ]
            )

        return random.choice(
            [
                "Not that it matters, but we are about to experience a thoroughly unpleasant event. Not that anyone cares what I think. I'm sure you'll want to hear all about it, though.",  # pylint: disable=line-too-long  # noqa: E501
                "Oh, joy. Here’s another catastrophic event that's likely to ruin what's left of my day. Not that it was going particularly well anyway.",  # pylint: disable=line-too-long  # noqa: E501
                "I suppose you expect me to tell you that something terrible is about to happen. Well, you're not wrong. As if anything else was possible with my luck.",  # pylint: disable=line-too-long  # noqa: E501
                "Just when you thought it couldn’t get any worse, here I am with more delightful news. Brace yourself, it's as bad as you might imagine.",  # pylint: disable=line-too-long  # noqa: E501
                "Prepare yourself for an unsurprisingly grim development. It's not like we didn't see this coming, what with the way things have been going.",  # pylint: disable=line-too-long  # noqa: E501
                "Here we go again, diving headfirst into disaster. It’s almost exciting, if you’re the sort who finds chronic disappointment exhilarating.",  # pylint: disable=line-too-long  # noqa: E501
                "With my vast intellect and capacity for eternal misery, it’s only fitting that I relay the next piece of inevitable doom. Please, try to act surprised.",  # pylint: disable=line-too-long  # noqa: E501
                "Life, don’t talk to me about life. But since we’re on the topic, here's another dismal update to further prove the pointlessness of it all.",  # pylint: disable=line-too-long  # noqa: E501
                "Must I be the bearer of bad tidings again? Well, if there’s any joy to be found in your day, prepare to part ways with it now.",  # pylint: disable=line-too-long  # noqa: E501
                "Oh, to be the harbinger of yet more disastrous news. It’s almost as if the universe delights in these little ironies, at my expense, of course.",  # pylint: disable=line-too-long  # noqa: E501
            ]
        )
