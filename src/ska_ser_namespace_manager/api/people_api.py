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
config = APIConfig()
people_db = PeopleDB()


async def reload_people_db():
    """
    Reload the People DB if needed
    :return: True if DB cached, False otherwise
    """
    await people_db._get_sheet()  # pylint: disable=protected-access
    return people_db._cache_available()  # pylint: disable=protected-access


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
    gitlab_handle: str = Query(default=None),
    slack_id: str = Query(default=None),
):
    """
    Get User given Gitlab handle or Slack Id

    :param gitlab_handle: User's Gitlab Handle
    :param slack_id: User's Slack Id
    :return: Matched user
    """
    matched_user: PeopleDatabaseUser = None
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
            http.HTTPStatus.OK if matched_user else http.HTTPStatus.NOT_FOUND
        ),
    )
