"""
This module provides the a generic Controller class to build
other controllers

Usage:
    To use this module, create an instance of Controller or inherit
    from it and call the run() method.
    Example:
        Controller().run()
"""

import datetime
import functools
import logging
import signal
import threading
from collections import defaultdict

import wrapt
from pydantic import BaseModel

from ska_ser_namespace_manager.core.config import ConfigLoader


class Controller:
    """
    A generic controller class to implement simple process
    management tasks
    """

    shutdown_event: threading.Event
    config: BaseModel
    threads: dict[str, threading.Thread]

    def __init__(
        self, config_class: type, tasks: list[callable] | None
    ) -> None:
        """
        Initialize the Controller

        :param config_class: Class to use to load configs
        :param tasks: List of tasks to manage
        """
        self.shutdown_event = threading.Event()
        self.config = ConfigLoader().load(config_class)
        self.threads = defaultdict(threading.Thread)
        for task in tasks:
            logging.info("Managing task '%s'", task.__name__)
            self.threads[task.__name__] = threading.Thread(target=task)

        signal.signal(signal.SIGINT, self.__shutdown__)
        signal.signal(signal.SIGTERM, self.__shutdown__)

    def __shutdown__(
        self, signum: int, frame  # pylint: disable=unused-argument
    ) -> None:
        """
        Handle the shutdown signal.

        :param signum: Signal number
        :param frame: Current stack frame
        :return:
        """
        logging.info("Received shutdown signal: %s [%s]", signum, frame)
        self.shutdown_event.set()

    def run(self) -> None:
        """
        Run the Controller.
        """
        for _, thread in self.threads.items():
            thread.start()

        logging.info("Waiting threads to complete ...")
        for task, thread in self.threads.items():
            thread.join()
            logging.info("Thread for task '%s' completed", task)


def ControllerTask(  # pylint: disable=invalid-name
    wrapped=None, period=datetime.timedelta(milliseconds=1000)
):
    """
    ControllerTask decorator allows to wrap the looping behavior for tasks

    :param wrapped: Function wrapped with the decorator
    :param period: Function calling period
    :return: Wrapped function implementing a periodic call of a function
    """
    if wrapped is None:
        return functools.partial(ControllerTask, period=period)

    @wrapt.decorator
    def wrapper(wrapped, instance: Controller, args, kwargs):
        while not instance.shutdown_event.is_set():
            wrapped(*args, **kwargs)

            if instance.shutdown_event.wait(timeout=period.total_seconds()):
                break

    return wrapper(wrapped)  # pylint: disable=no-value-for-parameter
