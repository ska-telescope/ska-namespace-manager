"""logging is a wrapper module to setup the logging format"""

import logging
import os

LOGGING_FORMAT = "%(asctime)s [level=%(levelname)s]: %(message)s"
logging.basicConfig(
    level=logging.getLevelName(os.environ.get("LOG_LEVEL", "INFO")),
    format=LOGGING_FORMAT,
)
