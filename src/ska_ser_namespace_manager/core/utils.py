"""
utils provides utility classes and functions
"""

import base64
import datetime
import json
import re
from typing import Any, Tuple

import pytz
from starlette.requests import Request

UNITS = {
    "s": "seconds",
    "m": "minutes",
    "h": "hours",
    "d": "days",
    "w": "weeks",
}


class Singleton(type):
    """
    Singleton implements the singleton pattern to be used as a
    metaclass for classes that are singletons
    """

    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(
                *args, **kwargs
            )

        return cls._instances[cls]


def deserialize_request(request: Request):  # pragma: no cover
    """
    Deserializes request into useful information for debugging

    :param request: Request that originated an debuggable event
    """
    return json.dumps(
        {
            "url": str(request.url),
            "headers": {
                header[0]: header[1] for header in request.headers.items()
            },
        },
        indent=4,
    )


def parse_timedelta(v: Any) -> datetime.timedelta:
    """
    Parses string to timedelta

    :param v: Input time delta
    :return: Timedelta as datetime.timedelta
    """
    timedelta = str(v)
    return datetime.timedelta(
        **{
            UNITS.get(m.group("unit").lower(), "seconds"): float(
                m.group("val")
            )
            for m in re.finditer(
                r"(?P<val>\d+(\.\d+)?)(?P<unit>[smhdw])",
                timedelta.replace(" ", ""),
                flags=re.I,
            )
        }
    )


def now() -> str:
    """
    Gets now date as UTC in ISO8601 format
    """
    return datetime.datetime.now(pytz.UTC).isoformat().replace("+00:00", "Z")


def encode_slack_address(slack_id: str, name: str) -> str:
    """
    Encodes the slack id and user name in base64
    """
    return base64.b64encode(f"{slack_id}::{name}".encode("utf-8")).decode(
        "utf-8"
    )


def decode_slack_address(address: str) -> Tuple[str, str]:
    """
    Decodes the slack id and user name from base64
    """
    if address in [None, ""]:
        return None, None

    return tuple(base64.b64decode(address).decode("utf-8").split("::"))
