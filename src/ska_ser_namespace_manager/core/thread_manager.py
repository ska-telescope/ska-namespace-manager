"""
thread_manager provides a central way of managing threaded tasks
"""

import logging
import signal
import threading
from typing import Any, Callable, List, TypeVar

T = TypeVar("T")


class ThreadManager:
    """
    A class to manage threads and handle shutdown signals.
    """

    def __init__(self):
        """
        Initialize the ThreadManager.
        """
        self.shutdown_event = threading.Event()
        self.threads: dict[str, threading.Thread] = {}
        self.task_stop_events: dict[str, threading.Event | None] = {}
        self._wake = threading.Condition()
        self.is_running = False
        signal.signal(signal.SIGINT, self.__shutdown)
        signal.signal(signal.SIGTERM, self.__shutdown)

    def add_tasks(self, tasks: List[Callable]) -> None:
        """
        Add tasks to the thread manager.
        """
        for task in tasks:
            self.__register_task(task.__name__, task)

    def add_managed_task(
        self,
        task_name: str,
        task: Callable[..., None],
        args: tuple[Any, ...] = (),
    ) -> None:
        """
        Add a managed task with its own stop event.
        """
        stop_event = threading.Event()
        self.__register_task(task_name, task, stop_event, (stop_event, *args))

    def has_task(self, task_name: str) -> bool:
        """
        Check if a task is already registered.
        """
        return task_name in self.threads

    def remove_task(self, task_name: str) -> None:
        """
        Stop and remove a single task.
        """
        stop_event = self.task_stop_events.pop(task_name, None)
        if stop_event is not None:
            stop_event.set()
            with self._wake:
                self._wake.notify_all()

        thread = self.threads.pop(task_name, None)
        if thread and thread.is_alive():
            thread.join()
            logging.debug("Thread for task '%s' completed", task_name)

    def wait_for_task_stop(
        self, stop_event: threading.Event, timeout: float
    ) -> bool:
        """
        Wait until either the controller or task stop event is set.
        """
        with self._wake:
            return self._wake.wait_for(
                lambda: self.shutdown_event.is_set() or stop_event.is_set(),
                timeout=timeout,
            )

    def terminate(self):
        """
        Signal the manager to terminate.
        """
        self.shutdown_event.set()
        for stop_event in self.task_stop_events.values():
            if stop_event is not None:
                stop_event.set()
        with self._wake:
            self._wake.notify_all()

    def __shutdown(
        self, signum: int, frame  # pylint: disable=unused-argument
    ) -> None:
        """
        Handle the shutdown signal.

        :param signum: Signal number
        :param frame: Current stack frame
        """
        logging.info("Received shutdown signal: %s [%s]", signum, frame)
        self.terminate()

    def run(self, blocking: bool = True) -> None:
        """
        Run the manager.

        :param blocking: If true, blocks the main loop until all threads
        complete. If false, doesn't block but requires manual cleanup of
        threads.
        """
        self.is_running = True
        for _, thread in self.threads.items():
            if not thread.is_alive():
                thread.start()

        if blocking:
            self.cleanup(terminate=False)

    def cleanup(self, terminate: bool = True) -> None:
        """
        Cleanup resources
        """
        if terminate:
            self.terminate()
        for task, thread in self.threads.items():
            if thread.is_alive():
                thread.join()
                logging.debug("Thread for task '%s' completed", task)
        self.is_running = False

    def __register_task(
        self,
        task_name: str,
        task: Callable,
        stop_event: threading.Event | None = None,
        args: tuple[Any, ...] = (),
    ) -> None:
        """
        Register a task and start it immediately if the manager is running.
        """
        logging.info("Managing task '%s'", task_name)
        thread = threading.Thread(target=task, args=args, name=task_name)
        self.threads[task_name] = thread
        self.task_stop_events[task_name] = stop_event
        if self.is_running:
            thread.start()
