"""
gitlab_pipeline_client provides reusable GitLab pipeline lookups
"""

import asyncio
import queue
import threading
from collections import deque
from concurrent.futures import Future
from datetime import datetime, timezone
from typing import Optional

import aiohttp
from gidgetlab import HTTPException, RateLimitExceeded
from ska_cicd_services_api.gitlab_api import GitLabApi

from ska_ser_namespace_manager.controller.collect_controller_config import (
    GitLabConfig,
)
from ska_ser_namespace_manager.core.logging import logging

NOT_FOUND_STATUS = "not_found"
CANCELED_STATUS = "canceled"


class GitLabPipelineClient:
    """
    GitLabPipelineClient owns a reusable GitLab API client and aiohttp session.

    Namespace checks run from normal controller threads, while the services
    API GitLab client is asynchronous. This class keeps one background event
    loop and session so callers can do thread-safe synchronous pipeline lookups
    without creating a new aiohttp session for every cache miss.
    """

    def __init__(self, config: GitLabConfig) -> None:
        """
        Initialize client state without starting the background loop.
        """
        self.config = config
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._requests = queue.Queue()
        self._session: Optional[aiohttp.ClientSession] = None
        self._api: Optional[GitLabApi] = None
        self._startup_error: Optional[BaseException] = None
        self._pipeline_status_cache = {}
        self._pipeline_status_cache_queue = deque()

    async def _initialize(self) -> None:
        """
        Initialize async resources on the background loop.
        """
        self._session = aiohttp.ClientSession()
        self._api = GitLabApi(
            self._session,
            api_base=self.config.api_base,
            gitlab_api_requester=self.config.requester or "",
            gitlab_api_private_token=self.config.private_token or "",
        )

    def _process_request(self, request) -> None:
        """
        Process a single synchronous lookup request.
        """
        project_id, pipeline_id, future = request
        if not future.set_running_or_notify_cancel():
            return

        try:
            future.set_result(
                asyncio.get_event_loop().run_until_complete(
                    self._get_pipeline_info(project_id, pipeline_id)
                )
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            future.set_exception(exc)

    def _run_worker(self) -> None:
        """
        Run GitLab lookups on the worker thread's event loop.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._initialize())
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self._startup_error = exc
            logging.error(
                "Failed to initialize GitLab pipeline client: %s", exc
            )
            self._ready.set()
            return

        self._ready.set()
        try:
            while True:
                request = self._requests.get()
                if request is None:
                    break

                self._process_request(request)
        finally:
            loop.run_until_complete(self._close_async())
            loop.close()
            self._ready.clear()

    def _start(self) -> None:
        """
        Start the background event loop if it is not already running.
        """
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return

            self._startup_error = None
            self._ready.clear()
            self._thread = threading.Thread(
                target=self._run_worker,
                name="gitlab-pipeline-client",
                daemon=True,
            )
            self._thread.start()

        self._ready.wait()
        if self._startup_error is not None:
            raise RuntimeError(
                "GitLab pipeline client failed to initialize"
            ) from self._startup_error

    async def _close_async(self) -> None:
        """
        Close async resources on the background loop.
        """
        if self._session is not None and not self._session.closed:
            await self._session.close()

        self._session = None
        self._api = None

    def close(self) -> None:
        """
        Stop the background loop and close the aiohttp session.
        """
        thread = self._thread
        if thread is None:
            return

        self._requests.put(None)
        thread.join()
        self._thread = None

    def _get_cached_pipeline_status(
        self, cache_key: tuple[str, str], now: datetime
    ) -> Optional[str]:
        """
        Get a cached status if it is still fresh.
        """
        cached_status = self._pipeline_status_cache.get(cache_key)
        if cached_status is None:
            return None

        cached_at, status = cached_status
        if now - cached_at < self.config.cache_ttl:
            return status

        self._pipeline_status_cache.pop(cache_key, None)

        return None

    def _cache_pipeline_status(
        self, cache_key: tuple[str, str], now: datetime, status: str
    ) -> None:
        """
        Cache a status and evict oldest entries over the configured limit.
        """
        max_entries = max(self.config.cache_max_entries, 0)
        if max_entries == 0:
            return

        self._pipeline_status_cache[cache_key] = (now, status)
        self._pipeline_status_cache_queue.append((cache_key, now))
        while len(self._pipeline_status_cache) > max_entries:
            oldest_key, queued_at = self._pipeline_status_cache_queue.popleft()
            cached_status = self._pipeline_status_cache.get(oldest_key)
            if cached_status is not None and cached_status[0] == queued_at:
                del self._pipeline_status_cache[oldest_key]

    async def _get_pipeline_info(
        self, project_id: str, pipeline_id: str
    ) -> dict:
        """
        Fetch pipeline info on the background loop.
        """
        if self._api is None:
            raise RuntimeError("GitLab API client is not initialized")

        return await self._api.get_pipeline_info(project_id, pipeline_id)

    def get_pipeline_info(self, project_id: str, pipeline_id: str) -> dict:
        """
        Get GitLab pipeline info using the reusable async client.
        """
        self._start()
        future = Future()
        self._requests.put((project_id, pipeline_id, future))
        return future.result()

    def get_pipeline_status(
        self, project_id: str, pipeline_id: str
    ) -> Optional[str]:
        """
        Get a cached GitLab pipeline status.
        """
        cache_key = (project_id, pipeline_id)
        now = datetime.now(timezone.utc)
        cached_status = self._get_cached_pipeline_status(cache_key, now)
        if cached_status is not None:
            return cached_status

        status = None
        pipeline = None
        try:
            pipeline = self.get_pipeline_info(project_id, pipeline_id)
        except RateLimitExceeded:
            pass
        except HTTPException as exc:
            status_code = int(exc.status_code)
            if status_code == 404:
                status = NOT_FOUND_STATUS

            if status_code != 429:
                logging.warning(
                    "Failed to fetch GitLab pipeline '%s' in project '%s': %s",
                    pipeline_id,
                    project_id,
                    exc,
                )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.warning(
                "Failed to fetch GitLab pipeline '%s' in project '%s': %s",
                pipeline_id,
                project_id,
                exc,
            )

        if pipeline is not None:
            status = pipeline.get("status")

        if status is not None:
            self._cache_pipeline_status(cache_key, now, status)

        return status
