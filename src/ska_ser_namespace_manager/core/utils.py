"""
utils provides utility classes and functions
"""

import json

from starlette.requests import Request


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
