"""test_people_api tests the people api endpoints"""

import http
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from ska_cicd_services_api.people_database_api import PeopleDatabaseUser

from src.api import app


@pytest.mark.asyncio
async def test_not_found_email():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.get_user_by_email = AsyncMock(return_value=None)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?email=marvin")
            assert response.status_code == http.HTTPStatus.NOT_FOUND
            assert response.json() == {"status": "not found"}


@pytest.mark.asyncio
async def test_not_found_slack_id():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.get_user_by_slack_id = AsyncMock(return_value=None)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?slack_id=marvin")

            assert response.status_code == http.HTTPStatus.NOT_FOUND
            assert response.json() == {"status": "not found"}


@pytest.mark.asyncio
async def test_not_found_gitlab_handle():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.get_user_by_gitlab_handle = AsyncMock(return_value=None)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?gitlab_handle=marvin")
            assert response.status_code == http.HTTPStatus.NOT_FOUND
            assert response.json() == {"status": "not found"}


@pytest.mark.asyncio
async def test_not_found_all():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.get_user_by_email = AsyncMock(return_value=None)
        mock_people_db.get_user_by_slack_id = AsyncMock(return_value=None)
        mock_people_db.get_user_by_gitlab_handle = AsyncMock(return_value=None)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get(
                "/api/people?email=marvin&slack_id=marvin&gitlab_handle=marvin"
            )

            assert response.status_code == http.HTTPStatus.NOT_FOUND
            assert response.json() == {"status": "not found"}


@pytest.mark.asyncio
async def test_not_found_ignore():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.get_user_by_email = AsyncMock(return_value=None)
        mock_people_db.get_user_by_slack_id = AsyncMock(return_value=None)
        mock_people_db.get_user_by_gitlab_handle = AsyncMock(return_value=None)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?email=&ignore_not_found=true")

            assert response.status_code == http.HTTPStatus.OK
            assert response.json() == {"status": "not found"}


@pytest.mark.asyncio
async def test_email():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        user = PeopleDatabaseUser(
            name="marvin",
            email="marvin@space.com",
            team="panic",
            slack_id="marvin",
            gitlab_handle="marvin",
        )
        mock_people_db.get_user_by_email = AsyncMock(return_value=user)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?email=marvin")
            assert response.status_code == http.HTTPStatus.OK
            assert response.json() == user.model_dump()


@pytest.mark.asyncio
async def test_slack_id():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        user = PeopleDatabaseUser(
            name="marvin",
            email="marvin@space.com",
            team="panic",
            slack_id="marvin",
            gitlab_handle="marvin",
        )
        mock_people_db.get_user_by_slack_id = AsyncMock(return_value=user)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?slack_id=marvin")

            assert response.status_code == http.HTTPStatus.OK
            assert response.json() == user.model_dump()


@pytest.mark.asyncio
async def test_gitlab_handle():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        user = PeopleDatabaseUser(
            name="marvin",
            email="marvin@space.com",
            team="panic",
            slack_id="marvin",
            gitlab_handle="marvin",
        )
        mock_people_db.get_user_by_gitlab_handle = AsyncMock(return_value=user)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?gitlab_handle=marvin")
            assert response.status_code == http.HTTPStatus.OK
            assert response.json() == user.model_dump()
