"""test_healt_api tests health endpoints of the api"""

import http
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.api import app


@pytest.mark.asyncio
async def test_liveness():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health/liveness")
        assert response.status_code == http.HTTPStatus.OK
        assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_ready():
    with patch(
        "src.api.apis_ready", new_callable=AsyncMock
    ) as mock_apis_ready:
        mock_apis_ready.return_value = True
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/health/readiness")
            assert response.status_code == http.HTTPStatus.OK
            assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readiness_not_ready():
    with patch(
        "src.api.apis_ready", new_callable=AsyncMock
    ) as mock_apis_ready:
        mock_apis_ready.return_value = False
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/health/readiness")
            assert (
                response.status_code == http.HTTPStatus.INTERNAL_SERVER_ERROR
            )
            assert response.json() == {"status": "error"}
