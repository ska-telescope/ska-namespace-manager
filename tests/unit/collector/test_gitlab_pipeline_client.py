"""Tests for reusable GitLab pipeline client behavior."""

import http
from collections import deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from gidgetlab import HTTPException, RateLimitExceeded

from ska_ser_namespace_manager.collector.gitlab_pipeline_client import (
    NOT_FOUND_STATUS,
    GitLabPipelineClient,
)


class FakeSession:
    """Minimal aiohttp session replacement for client lifecycle tests."""

    instances = []

    def __init__(self):
        """Record created sessions."""
        self.closed = False
        self.__class__.instances.append(self)

    async def close(self):
        """Mark the fake session closed."""
        self.closed = True


class FakeGitLabApi:
    """Minimal services API GitLab client replacement."""

    instances = []

    def __init__(
        self,
        session,
        api_base,
        gitlab_api_requester,
        gitlab_api_private_token,
    ):
        """Record constructor arguments for assertions."""
        self.session = session
        self.api_base = api_base
        self.gitlab_api_requester = gitlab_api_requester
        self.gitlab_api_private_token = gitlab_api_private_token
        self.calls = []
        self.__class__.instances.append(self)

    async def get_pipeline_info(self, project_id, pipeline_id):
        """Return pipeline status and record calls."""
        self.calls.append((project_id, pipeline_id))
        return {"status": "running"}


def test_gitlab_pipeline_client_reuses_session_and_api():
    """Multiple lookups should reuse one session and services API client."""
    FakeSession.instances = []
    FakeGitLabApi.instances = []
    config = SimpleNamespace(
        api_base="https://gitlab.example.test",
        requester="namespace-manager",
        private_token="token",
        cache_ttl=timedelta(minutes=5),
        cache_max_entries=10000,
    )

    with patch(
        "ska_ser_namespace_manager.collector.gitlab_pipeline_client.aiohttp.ClientSession",  # pylint: disable=line-too-long # noqa: E501
        FakeSession,
    ), patch(
        "ska_ser_namespace_manager.collector.gitlab_pipeline_client.GitLabApi",
        FakeGitLabApi,
    ):
        client = GitLabPipelineClient(config)
        try:
            assert client.get_pipeline_info("123", "456") == {
                "status": "running"
            }
            assert client.get_pipeline_info("123", "789") == {
                "status": "running"
            }
        finally:
            client.close()

    assert len(FakeSession.instances) == 1
    assert len(FakeGitLabApi.instances) == 1
    assert FakeGitLabApi.instances[0].calls == [
        ("123", "456"),
        ("123", "789"),
    ]
    assert FakeGitLabApi.instances[0].api_base == "https://gitlab.example.test"
    assert FakeGitLabApi.instances[0].gitlab_api_requester == (
        "namespace-manager"
    )
    assert FakeGitLabApi.instances[0].gitlab_api_private_token == "token"
    assert FakeSession.instances[0].closed is True


def test_gitlab_pipeline_client_caches_status():
    """Status lookups should use the client cache."""
    FakeSession.instances = []
    FakeGitLabApi.instances = []
    config = SimpleNamespace(
        api_base="https://gitlab.example.test",
        requester="namespace-manager",
        private_token="token",
        cache_ttl=timedelta(minutes=5),
        cache_max_entries=10000,
    )

    with patch(
        "ska_ser_namespace_manager.collector.gitlab_pipeline_client.aiohttp.ClientSession",  # pylint: disable=line-too-long # noqa: E501
        FakeSession,
    ), patch(
        "ska_ser_namespace_manager.collector.gitlab_pipeline_client.GitLabApi",
        FakeGitLabApi,
    ):
        client = GitLabPipelineClient(config)
        try:
            assert client.get_pipeline_status("123", "456") == "running"
            assert client.get_pipeline_status("123", "456") == "running"
        finally:
            client.close()

    assert len(FakeGitLabApi.instances) == 1
    assert FakeGitLabApi.instances[0].calls == [("123", "456")]


def test_gitlab_pipeline_client_refreshes_expired_requested_key():
    """Expired requested status cache entries should be refreshed."""
    config = SimpleNamespace(
        cache_ttl=timedelta(minutes=5), cache_max_entries=10
    )
    client = GitLabPipelineClient(config)
    client._pipeline_status_cache = {  # pylint: disable=protected-access
        ("old", "1"): (datetime(2024, 1, 1, tzinfo=timezone.utc), "running"),
    }
    client._pipeline_status_cache_queue = (
        deque(  # pylint: disable=protected-access
            [(("old", "1"), datetime(2024, 1, 1, tzinfo=timezone.utc))]
        )
    )
    client.get_pipeline_info = lambda _project_id, _pipeline_id: {
        "status": "success"
    }

    assert client.get_pipeline_status("old", "1") == "success"
    assert (
        client._pipeline_status_cache[("old", "1")][1] == "success"
    )  # pylint: disable=protected-access


def test_gitlab_pipeline_client_evicts_oldest_status_when_cache_full():
    """Oldest status cache entries should be evicted over max size."""
    config = SimpleNamespace(cache_ttl=timedelta(days=1), cache_max_entries=2)
    client = GitLabPipelineClient(config)
    now = datetime.now(timezone.utc)
    client._pipeline_status_cache = {  # pylint: disable=protected-access
        ("oldest", "1"): (
            now - timedelta(minutes=2),
            "running",
        ),
        ("older", "2"): (
            now - timedelta(minutes=1),
            "running",
        ),
    }
    client._pipeline_status_cache_queue = (
        deque(  # pylint: disable=protected-access
            [
                (("oldest", "1"), now - timedelta(minutes=2)),
                (("older", "2"), now - timedelta(minutes=1)),
            ]
        )
    )
    client.get_pipeline_info = lambda _project_id, _pipeline_id: {
        "status": "success"
    }

    assert client.get_pipeline_status("new", "3") == "success"
    assert (
        len(client._pipeline_status_cache) == 2
    )  # pylint: disable=protected-access
    assert (
        "oldest",
        "1",
    ) not in client._pipeline_status_cache  # pylint: disable=protected-access
    assert list(
        client._pipeline_status_cache_queue
    ) == [  # pylint: disable=protected-access
        (("older", "2"), now - timedelta(minutes=1)),
        (
            ("new", "3"),
            client._pipeline_status_cache[("new", "3")][0],
        ),  # pylint: disable=protected-access
    ]


def test_gitlab_pipeline_client_handles_not_found():
    """GitLab 404 should be interpreted as a deleted pipeline."""
    config = SimpleNamespace(
        cache_ttl=timedelta(minutes=5), cache_max_entries=10
    )
    client = GitLabPipelineClient(config)
    client.get_pipeline_info = lambda _project_id, _pipeline_id: (
        _ for _ in ()
    ).throw(  # pylint: disable=line-too-long # noqa: E501
        HTTPException(http.HTTPStatus.NOT_FOUND)
    )

    assert client.get_pipeline_status("123", "456") == NOT_FOUND_STATUS


def test_gitlab_pipeline_client_handles_rate_limit():
    """GitLab rate limiting should be inconclusive."""
    config = SimpleNamespace(
        cache_ttl=timedelta(minutes=5), cache_max_entries=10
    )
    client = GitLabPipelineClient(config)
    client.get_pipeline_info = lambda _project_id, _pipeline_id: (
        _ for _ in ()
    ).throw(  # pylint: disable=line-too-long # noqa: E501
        RateLimitExceeded(None)
    )

    assert client.get_pipeline_status("123", "456") is None
