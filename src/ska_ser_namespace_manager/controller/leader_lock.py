"""leader_lock implements a filelock based leader election lock"""

import datetime
import logging
import os
import traceback
from pathlib import Path

from filelock import FileLock, Timeout


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

    def __init__(
        self, lock_path: str, lease_path: str, lease_ttl: datetime.timedelta
    ) -> None:
        self.lock_path = lock_path
        self.lease_path = lease_path
        self.lease_ttl = lease_ttl
        self.file_lock = FileLock(lock_path, thread_local=False)
        self.lease_lock = FileLock(lease_path, thread_local=False)

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
                self.file_lock.acquire(timeout=1)
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
                modification_time = datetime.datetime.fromtimestamp(
                    stat.st_mtime
                )
                if (
                    datetime.datetime.now() - modification_time
                ) > self.lease_ttl:  # stale lease detected
                    logging.info(
                        "Detected stale lease. Attempting to acquire lock ..."
                    )
                    with self.lease_lock.acquire(timeout=-1, blocking=False):
                        os.remove(self.lock_path)
                        self.file_lock.acquire(timeout=-1, blocking=False)

                    os.remove(self.lease_path)

        except Timeout as exc:
            logging.error("Failed to force-acquire leader lock")
            traceback.print_exception(exc)
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
        Tells if this is the leader

        :return: True if it is the leader, False otherwise
        """

        return self.file_lock.is_locked

    def release(self):
        """
        Releases the lock

        :return:
        """

        if self.is_leader():
            self.file_lock.release(force=True)
