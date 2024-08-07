"""
thread_manager provides a central way of managing threaded tasks
"""

import logging
import signal
import threading
from collections import defaultdict
from typing import Callable, List, TypeVar

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
        self.threads = defaultdict(threading.Thread)
        signal.signal(signal.SIGINT, self.__shutdown)
        signal.signal(signal.SIGTERM, self.__shutdown)

    def add_tasks(self, tasks: List[Callable]) -> None:
        """
        Add tasks to the thread manager.
        """
        for task in tasks:
            logging.info("Managing task '%s'", task.__name__)
            self.threads[task.__name__] = threading.Thread(target=task)

    def terminate(self):
        """
        Signal the manager to terminate.
        """
        self.shutdown_event.set()

    def __shutdown(
        self, signum: int, frame  # pylint: disable=unused-argument
    ) -> None:
        """
        Handle the shutdown signal.

        :param signum: Signal number
        :param frame: Current stack frame
        """
        logging.info("Received shutdown signal: %s [%s]", signum, frame)
        self.shutdown_event.set()

    def run(self, blocking: bool = True) -> None:
        """
        Run the manager.

        :param blocking: If true, blocks the main loop until all threads
        complete. If false, doesn't block but requires manual cleanup of
        threads.
        """
        for _, thread in self.threads.items():
            thread.start()

        if blocking:
            self.cleanup()

    def cleanup(self) -> None:
        """
        Cleanup resources
        """
        for task, thread in self.threads.items():
            if thread.is_alive():
                thread.join()
                logging.debug("Thread for task '%s' completed", task)
