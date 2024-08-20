"""
metrics_api exposes the namespace manager metrics
"""

from fastapi import APIRouter
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST

from ska_ser_namespace_manager.api.metrics import Metrics

api = APIRouter()


@api.get(
    "",
    response_model=bytes,
    summary="Get metrics",
    description="""
Get the Namespace Manager metrics
""",
    responses={
        200: {"description": "Prometheus metrics"},
    },
)
async def handle_get_metrics():
    """
    Get the Namespace Manager metrics
    :return: Prometheus metrics
    """
    metrics = Metrics()
    return Response(metrics.get_metrics(), media_type=CONTENT_TYPE_LATEST)
