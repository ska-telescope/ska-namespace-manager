import datetime
import os
import tempfile
import time

import filelock
import pytest

from ska_ser_namespace_manager.controller.leader_lock import LeaderLock


@pytest.fixture()
def with_temp_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


TIMEOUT = 0.1
LEASE_TTL = 0.5


class TestLeaderLock:
    def test_lock_acquire_renew_release(self, with_temp_dir):
        lock_file_path = os.path.join(with_temp_dir, "lock")
        lock = LeaderLock(
            lock_path=lock_file_path,
            lease_path=os.path.join(with_temp_dir, "lease"),
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
        )

        lock.acquire_lease()
        stat_before = os.stat(lock_file_path)

        assert lock.is_leader()

        time.sleep(LEASE_TTL)

        lock.renew_lease()
        stat_after = os.stat(lock_file_path)

        assert lock.is_leader()
        assert stat_after.st_atime > stat_before.st_atime

        lock.release()

        assert not lock.is_leader()

    def test_lock_multiple_acquire_renew_release(self, with_temp_dir):
        lock_file_path = os.path.join(with_temp_dir, "lock")
        lease_file_path = os.path.join(with_temp_dir, "lease")
        lock1 = LeaderLock(
            lock_path=lock_file_path,
            lease_path=lease_file_path,
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
        )
        lock2 = LeaderLock(
            lock_path=lock_file_path,
            lease_path=lease_file_path,
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
        )

        lock1.acquire_lease()
        lock2.acquire_lease()

        assert lock1.is_leader()
        assert not lock2.is_leader()

        lock2.acquire_lease()
        lock1.acquire_lease()

        assert lock1.is_leader()
        assert not lock2.is_leader()

        lock1.release()
        lock2.release()

        assert not lock1.is_leader()
        assert not lock2.is_leader()

        lock2.acquire_lease()
        lock1.acquire_lease()

        assert lock2.is_leader()
        assert not lock1.is_leader()

        lock1.release()
        lock2.release()

        assert not lock1.is_leader()
        assert not lock2.is_leader()

    def test_lock_stale(self, with_temp_dir):
        lock_file_path = os.path.join(with_temp_dir, "lock")
        lease_file_path = os.path.join(with_temp_dir, "lease")
        lock1 = LeaderLock(
            lock_path=lock_file_path,
            lease_path=lease_file_path,
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
        )
        lock2 = LeaderLock(
            lock_path=lock_file_path,
            lease_path=lease_file_path,
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
        )

        lock1.acquire_lease()
        lock2.acquire_lease()

        assert lock1.is_leader()
        assert not lock2.is_leader()

        time.sleep(LEASE_TTL)

        lock2.acquire_lease()
        lock1.acquire_lease()

        assert not lock2.is_leader()
        assert lock1.is_leader()

        time.sleep(LEASE_TTL * 2)

        lock2.acquire_lease()
        lock1.acquire_lease()

        assert lock2.is_leader()
        assert not lock1.is_leader()

        lock1.release()
        lock2.release()

        assert not lock1.is_leader()
        assert not lock2.is_leader()

    def test_fail_lock_stale(self, with_temp_dir):
        lock_file_path = os.path.join(with_temp_dir, "lock")
        lease_file_path = os.path.join(with_temp_dir, "lease")
        lock1 = LeaderLock(
            lock_path=lock_file_path,
            lease_path=lease_file_path,
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
            rethrow_exception=True,
        )
        lock2 = LeaderLock(
            lock_path=lock_file_path,
            lease_path=lease_file_path,
            lease_ttl=datetime.timedelta(seconds=LEASE_TTL),
            timeout=TIMEOUT,
            rethrow_exception=True,
        )

        lock1.acquire_lease()
        lock2.acquire_lease()

        assert lock1.is_leader()
        assert not lock2.is_leader()

        time.sleep(LEASE_TTL * 2)

        lock1.lease_lock.acquire(timeout=-1)
        with pytest.raises(filelock._error.Timeout):
            lock2.acquire_lease()

        lock1.lease_lock.release()
        lock1.acquire_lease()

        assert lock1.is_leader()
        assert not lock2.is_leader()

        lock1.release()
        lock2.release()

        assert not lock1.is_leader()
        assert not lock2.is_leader()
