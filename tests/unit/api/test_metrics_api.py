"""test_metrics_api tests the metrics api endpoints"""

import http
from unittest.mock import Mock, patch

import pytest
from httpx import AsyncClient
from prometheus_client import CONTENT_TYPE_LATEST

from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig
from src.api import app


@pytest.mark.asyncio
async def test_metrics():
    with patch(
        "ska_ser_namespace_manager.api.metrics_api.Metrics", autospec=True
    ) as mock_metrics_class:
        mock_metrics = mock_metrics_class.return_value
        mock_metrics.config = MetricsConfig()
        metrics = "some_metrics".encode("utf-8")
        mock_metrics.get_metrics = Mock(return_value=metrics)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/metrics")
            assert response.status_code == http.HTTPStatus.OK
            assert response.headers.get("Content-Type", CONTENT_TYPE_LATEST)
            assert response.read() == metrics
