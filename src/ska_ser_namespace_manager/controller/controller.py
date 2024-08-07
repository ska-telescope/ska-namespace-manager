"""
controller provides the a generic Controller class to build
other controllers
"""

import datetime
import functools
import traceback
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
from ska_ser_namespace_manager.core.thread_manager import ThreadManager

T = TypeVar("T", bound=ControllerConfig)


class Controller(KubernetesAPI, ThreadManager):
    """
    A generic controller class to implement simple process
    management tasks
    """

    config: BaseModel
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
        KubernetesAPI.__init__(self, kubeconfig)
        ThreadManager.__init__(self)
        self.config: T = ConfigLoader().load(config_class)
        self.template_factory = TemplateFactory()
        self.forbidden_namespaces = FORBIDDEN_NAMESPACES + [
            self.config.context.namespace
        ]
        self.add_tasks(tasks)


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
                logging.debug(f"Starting task {wrapped.__name__}")
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
                logging.debug(f"Terminating task {wrapped.__name__}")
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
                    logging.debug(
                        f"Starting conditional task {wrapped.__name__}"
                    )
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
                logging.debug(
                    f"Terminating conditional task {wrapped.__name__}"
                )
                break

    return wrapper(wrapped)  # pylint: disable=no-value-for-parameter
