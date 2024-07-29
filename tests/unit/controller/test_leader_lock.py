import pytest
import tempfile
import os
import datetime

from ska_ser_namespace_manager.controller.leader_lock import LeaderLock

@pytest.fixture()
def with_temp_dir():
    with tempfile.TemporaryDirectory() as tmpdirname:
        yield tmpdirname


class TestLeaderLock:
    def test_lock_acquire_renew_release(self, with_temp_dir):
        lock_file_path = os.path.join(with_temp_dir, "lock")
        lock = LeaderLock(
            lock_path=lock_file_path,
            lease_path=os.path.join(with_temp_dir, "lease"),
            lease_ttl=datetime.timedelta(seconds=1)
        )
        
        lock.acquire_lease()
        stat_before = os.stat(lock_file_path)

        assert lock.is_leader()

        lock.renew_lease()
        stat_after = os.stat(lock_file_path)

        assert lock.is_leader()
        assert stat_after.st_mtime > stat_before.st_mtime

        lock.release()

        assert not lock.is_leader()
