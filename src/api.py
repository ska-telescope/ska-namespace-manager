#!/usr/bin/env python
"""
api provides a REST API to facilitate the integration of the Kuberentes API
with the SKA Namespace Manager ecosystem and the abstraction of data stores
"""

import http
import logging
import traceback
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ska_ser_namespace_manager.api.api_config import APIConfig
from ska_ser_namespace_manager.api.people_api import api as people_api
from ska_ser_namespace_manager.api.people_api import (
    is_ready as people_api_ready,
)
from ska_ser_namespace_manager.core.config import ConfigLoader
from ska_ser_namespace_manager.core.utils import deserialize_request


@asynccontextmanager
async def lifespan(_):
    """
    Lifespan hook. Do 'startup' operations before yield and
    'cleanup' operations after
    """
    yield


app = FastAPI(title="SKA Namespace Manager REST API", lifespan=lifespan)

api = APIRouter()


async def apis_ready() -> bool:
    """
    Return complete readiness of the API

    :return: True if the API is ready, false otherwise
    """
    return await people_api_ready()


@app.exception_handler(Exception)
async def exception_handler_request(request, exc):
    """
    Exception handler to return a standard HTTP response and log
    request information for debugging
    """
    traceback.print_exception(exc)
    logging.error(deserialize_request(request))
    return JSONResponse(
        content=jsonable_encoder({"exception": exc}),
        status_code=http.HTTPStatus.BAD_REQUEST,
    )


@app.exception_handler(RequestValidationError)
async def requestvalidation_exception_handler_request(request, exc):
    """
    Exception handler to return a standard HTTP response and log
    request information for debugging
    """
    traceback.print_exception(exc)
    logging.error(deserialize_request(request))
    return JSONResponse(
        content=jsonable_encoder({"exception": exc}),
        status_code=http.HTTPStatus.BAD_REQUEST,
    )


@app.get("/health/liveness")
async def liveness():
    """
    Returns the liveness of the API
    """
    return JSONResponse(
        content=jsonable_encoder({"status": "ok"}),
        status_code=http.HTTPStatus.OK,
    )


@app.get("/health/readiness")
async def readiness():
    """
    Returns the readiness of the API
    """
    ready = await apis_ready()
    return JSONResponse(
        content=jsonable_encoder({"status": "ok" if ready else "error"}),
        status_code=(
            http.HTTPStatus.OK
            if ready
            else http.HTTPStatus.INTERNAL_SERVER_ERROR
        ),
    )


api.include_router(people_api, prefix="/people")
app.include_router(api, prefix="/api")


if __name__ == "__main__":
    config: APIConfig
    config = ConfigLoader().load(APIConfig)
    uvicorn.run(
        "api:app",
        host="0.0.0.0",
        port=int(
            config.https_port if config.https_enabled else config.http_port
        ),
        reload=False,
        ssl_keyfile=config.key_path if config.https_enabled else None,
        ssl_certfile=config.cert_path if config.https_enabled else None,
    )
