"""
teams_api
"""

import http

from fastapi import APIRouter, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from ska_cicd_services_api.people_database_api import PeopleDatabaseUser

from ska_ser_namespace_manager.api.api_config import APIConfig
from ska_ser_namespace_manager.api.people_db import PeopleDB

api = APIRouter()


async def is_ready():
    """
    Check if the people api is ready
    :return: True if DB cached, False otherwise
    """
    config = APIConfig()
    return (
        await PeopleDB().refresh()
        or config.people_database.spreadsheet_id == "dummy"
    )


@api.get(
    "",
    response_model=PeopleDatabaseUser,
    summary="Get user",
    description="""
Get user given a Gitlab Handle or Slack ID
""",
    responses={
        200: {"description": "User found"},
        404: {"description": "User not found"},
    },
)
async def handle_get_user(
    email: str = Query(default=None),
    slack_id: str = Query(default=None),
    gitlab_handle: str = Query(default=None),
    ignore_not_found: bool = Query(default=False),
):
    """
    Get User given Gitlab handle or Slack Id

    :param email: User's email
    :param slack_id: User's Slack Id
    :param gitlab_handle: User's Gitlab Handle
    :param ignore_not_found: True if the API should return a 200
    even if the user is not found
    :return: Matched user
    """
    people_db = PeopleDB()
    matched_user: PeopleDatabaseUser = None

    if email:
        matched_user = await people_db.get_user_by_email(email)

    if gitlab_handle:
        matched_user = await people_db.get_user_by_gitlab_handle(gitlab_handle)

    if slack_id:
        matched_user = await people_db.get_user_by_slack_id(slack_id)

    return JSONResponse(
        content=(
            jsonable_encoder(matched_user)
            if matched_user
            else {"status": "not found"}
        ),
        status_code=(
            http.HTTPStatus.OK
            if matched_user or ignore_not_found
            else http.HTTPStatus.NOT_FOUND
        ),
    )
