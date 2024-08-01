"""
controller provides the a generic Controller class to build
other controllers
"""

import datetime
import functools
import signal
import threading
import traceback
from collections import defaultdict
from typing import Callable, List, Optional, TypeVar

import wrapt
from pydantic import BaseModel

from ska_ser_namespace_manager.controller.controller_config import (
    ControllerConfig,
)
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.kubernetes_api import KubernetesAPI
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import FORBIDDEN_NAMESPACES
from ska_ser_namespace_manager.core.template_factory import TemplateFactory

T = TypeVar("T", bound=ControllerConfig)


class Controller(KubernetesAPI):
    """
    A generic controller class to implement simple process
    management tasks
    """

    shutdown_event: threading.Event
    config: BaseModel
    threads: dict[str, threading.Thread]
    forbidden_namespaces: list[str]

    def __init__(
        self,
        config_class: T,
        tasks: List[Callable] | None,
        kubeconfig: Optional[str] = None,
    ) -> None:
        """
        Initialize the Controller

        :param config_class: Class to use to load configs
        :param tasks: List of tasks to manage
        :param kubeconfig: Kubeconfig to use
        """
        super().__init__(kubeconfig)
        self.shutdown_event = threading.Event()
        self.config: T = ConfigLoader().load(config_class)
        self.threads = defaultdict(threading.Thread)
        self.template_factory = TemplateFactory()
        self.forbidden_namespaces = FORBIDDEN_NAMESPACES + [
            self.config.context.namespace
        ]
        self.add_tasks(tasks)
        signal.signal(signal.SIGINT, self.__shutdown)
        signal.signal(signal.SIGTERM, self.__shutdown)

    def add_tasks(self, tasks: List[Callable]) -> None:
        """
        Add tasks to the task manager
        """
        for task in tasks:
            logging.info("Managing task '%s'", task.__name__)
            self.threads[task.__name__] = threading.Thread(target=task)

    def terminate(self):
        """
        Signal the controller to terminate
        :return:
        """
        self.shutdown_event.set()

    def __shutdown(
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

    def cleanup(self) -> None:
        """
        Cleanup resources

        :return:
        """

    def run(self) -> None:
        """
        Run the Controller.
        """
        for _, thread in self.threads.items():
            thread.start()

        for task, thread in self.threads.items():
            thread.join()
            logging.debug("Thread for task '%s' completed", task)

        self.cleanup()


def controller_task(
    wrapped=None,
    period: datetime.timedelta | Callable = datetime.timedelta(
        milliseconds=1000
    ),
):
    """
    controller_task decorator allows to wrap the looping behavior for tasks

    :param wrapped: Function wrapped with the decorator
    :param period: Function calling period
    :return: Wrapped function implementing a periodic call of a function
    """
    if wrapped is None:
        return functools.partial(controller_task, period=period)

    @wrapt.decorator
    def wrapper(wrapped, instance: Controller, args, kwargs):
        while not instance.shutdown_event.is_set():
            try:
                wrapped(*args, **kwargs)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                logging.error(
                    "Failure in task '%s': %s", wrapped.__name__, exc
                )
                traceback.print_exception(exc)

            if instance.shutdown_event.wait(
                timeout=(
                    period.total_seconds()
                    if isinstance(period, datetime.timedelta)
                    else period(instance)
                )
            ):
                break

    return wrapper(wrapped)  # pylint: disable=no-value-for-parameter


def conditional_controller_task(
    wrapped=None,
    period: datetime.timedelta | Callable = datetime.timedelta(
        milliseconds=1000
    ),
    run_if: Callable | bool | None = None,
):
    """
    ControllerTask decorator allows to wrap the looping behavior for tasks

    :param wrapped: Function wrapped with the decorator
    :param period: Function calling period
    :param run_if: Run function if True
    :return: Wrapped function implementing a periodic call of a function
    """
    if wrapped is None:
        return functools.partial(
            conditional_controller_task, period=period, run_if=run_if
        )

    @wrapt.decorator
    def wrapper(wrapped, instance: Controller, args, kwargs):
        while not instance.shutdown_event.is_set():
            run: bool = True
            if run_if is not None:
                if callable(run_if):
                    run = run_if(instance)
                else:
                    run = run_if

            if run:
                try:
                    wrapped(*args, **kwargs)
                except (
                    Exception  # pylint: disable=broad-exception-caught
                ) as exc:
                    logging.error(
                        "Failure in task '%s': %s", wrapped.__name__, exc
                    )
                    traceback.print_exception(exc)

            if instance.shutdown_event.wait(
                timeout=(
                    period.total_seconds()
                    if isinstance(period, datetime.timedelta)
                    else period(instance)
                )
            ):
                break

    return wrapper(wrapped)  # pylint: disable=no-value-for-parameter
