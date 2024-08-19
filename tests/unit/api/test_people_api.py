"""test_people_api tests the people api endpoints"""

import http
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from ska_cicd_services_api.people_database_api import PeopleDatabaseUser

from ska_ser_namespace_manager.api.api_config import (
    GoogleServiceAccount,
    PeopleDatabaseConfig,
)
from src.api import app

dummy_credentials = GoogleServiceAccount(
    project_id="dummy",
    private_key_id="dummy",
    private_key="-----BEGIN RSA PRIVATE KEY-----\
      MIIBOgIBAAJBAKj34GkxFhD90vcNLYLInFEX6Ppy1tPf9Cnzj4p4WGeKLs1Pt8Qu\
      KUpRKfFLfRYC9AIKjbJTWit+CqvjWYzvQwECAwEAAQJAIJLixBy2qpFoS4DSmoEm\
      o3qGy0t6z09AIJtH+5OeRV1be+N4cDYJKffGzDa88vQENZiRm0GRq6a+HPGQMd2k\
      TQIhAKMSvzIBnni7ot/OSie2TmJLY4SwTQAevXysE2RbFDYdAiEBCUEaRQnMnbp7\
      9mxDXDf6AU0cN/RPBjb9qSHDcWZHGzUCIG2Es59z8ugGrDY+pxLQnwfotadxd+Uy\
      v/Ow5T0q5gIJAiEAyS4RaI9YG8EWx/2w0T67ZUVAw8eOMB6BIUg0Xcu+3okCIBOs\
      /5OiPgoTdSy7bcF9IGpSE8ZgGKzgYQVZeN97YE00\
      -----END RSA PRIVATE KEY-----",
    client_email="dummy",
    client_id="dummy",
    client_x509_cert_url="dummy",
)


@pytest.mark.asyncio
async def test_not_found_email():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
        )
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
        )
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
        )
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
        )
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
        )
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
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
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
        )
        mock_people_db.get_user_by_gitlab_handle = AsyncMock(return_value=user)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?gitlab_handle=marvin")
            assert response.status_code == http.HTTPStatus.OK
            assert response.json() == user.model_dump()


@pytest.mark.asyncio
async def test_people_db_disabled():
    with patch(
        "ska_ser_namespace_manager.api.people_api.PeopleDB", autospec=True
    ) as mock_people_db_class:
        mock_people_db = mock_people_db_class.return_value
        mock_people_db.config = PeopleDatabaseConfig(
            credentials=dummy_credentials,
            spreadsheet_id="dummy",
            enabled=False,
        )
        mock_people_db.get_user_by_email = AsyncMock(return_value=None)
        mock_people_db.get_user_by_slack_id = AsyncMock(return_value=None)
        mock_people_db.get_user_by_gitlab_handle = AsyncMock(return_value=None)
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.get("/api/people?email=marvin")

            assert response.status_code == http.HTTPStatus.NOT_FOUND
            assert response.json() == {"status": "not found"}
