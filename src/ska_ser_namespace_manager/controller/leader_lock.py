"""leader_lock implements a filelock based leader election lock"""

import datetime
import fcntl
import os
import traceback
from contextlib import suppress
from pathlib import Path

from filelock import FileLock, Timeout

from ska_ser_namespace_manager.core.logging import logging


class LeaderLock:
    """
    LeaderLock implements a dead-lock safe leader lock by
    using a long-lived lock and a short-lived lock to override
    stale locks from other clients
    """

    lock_path: str
    lease_path: str
    lease_ttl: datetime.timedelta
    file_lock: FileLock
    timeout: float

    def __init__(
        self,
        lock_path: str,
        lease_path: str,
        lease_ttl: datetime.timedelta,
        timeout: float = 1,
        rethrow_exception: bool = False,
    ) -> None:
        self.lock_path = lock_path
        self.lease_path = lease_path
        self.lease_ttl = lease_ttl
        self.file_lock = FileLock(lock_path, thread_local=False)
        self.lease_lock = FileLock(lease_path, thread_local=False)
        self.timeout = timeout
        self.rethrow_exception = rethrow_exception

    def _drop_stale_handle(self) -> None:
        """
        Drops a stale local file descriptor without unlinking
        the current shared lock path.
        """
        context = (
            self.file_lock._context  # pylint: disable=protected-access  # noqa: E501
        )
        fd = context.lock_file_fd
        if fd is None:
            return

        context.lock_file_fd = None
        context.lock_counter = 0
        with suppress(OSError):
            fcntl.flock(fd, fcntl.LOCK_UN)
        with suppress(OSError):
            os.close(fd)

        self.file_lock = FileLock(self.lock_path, thread_local=False)

    def acquire_lease(self):
        """
        Attempts to acquire lease and in case of failure, tries to
        force acquire it if it deems the lease to be stale

        :return:
        """
        try:
            logging.debug("Attempting to acquire lock ...")
            if self.is_leader():
                self.renew_lease()
            else:
                # Drop the stale local handle before trying the
                # current shared lock path again.
                if self.file_lock.is_locked:
                    logging.warning("Dropping stale lock handle ...")
                    self._drop_stale_handle()

                self.file_lock.acquire(timeout=self.timeout)
                logging.info("Acquired leader lock")
        except Timeout:
            logging.debug("Failed to acquire leader lock")
            self.force_acquire_lease()

    def force_acquire_lease(self):
        """
        Force acquires the lock lease if it is stale. This is to
        prevent a dead lock by a client that never releases the lock

        :return:
        """
        try:
            if os.path.exists(self.lock_path):
                stat = os.stat(self.lock_path)
                lease_time = datetime.datetime.fromtimestamp(stat.st_atime)
                if (datetime.datetime.now() - lease_time) > 2 * self.lease_ttl:
                    logging.warning(
                        "Detected stale lease. Attempting to acquire stale lock ..."
                    )
                    with self.lease_lock.acquire(timeout=-1, blocking=False):
                        os.remove(self.lock_path)
                        self.file_lock.acquire(timeout=-1, blocking=False)

        except Timeout as exc:
            logging.error("Failed to force-acquire leader lock")
            traceback.print_exception(exc)
            if self.rethrow_exception:
                raise exc
        finally:
            if os.path.exists(self.lease_path):
                os.remove(self.lease_path)

    def renew_lease(self) -> None:
        """
        Renews the lock lease by touching the lock file

        :return:
        """
        logging.debug("Renewing lock lease ...")
        Path(self.lock_path).touch()

    def is_leader(self):
        """
        Tells if this is the leader. Also it checks the st_ino flag
        to understand if the underlying file changed and the lock we
        think we have is now stale

        :return: True if it is the leader, False otherwise
        """
        locked = self.file_lock.is_locked
        if locked and os.path.exists(self.lock_path):
            locked = (
                os.stat(self.lock_path).st_ino
                == os.fstat(
                    self.file_lock._context.lock_file_fd  # pylint: disable=protected-access  # noqa: E501
                ).st_ino
            )

        return locked

    def release(self):
        """
        Releases the lock

        :return:
        """

        if self.is_leader():
            self.file_lock.release(force=True)
