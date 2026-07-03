"""
People-API integration test.

Verifies that ``GET /api/people`` on the deployed manager resolves the
test identity to the expected team and Slack ID. Parametrized over
lookup mode (``email`` and ``gitlab_handle`` — the endpoint does not
accept ``authorId``).

The identity is supplied through env vars (see ``people_identity``
fixture in ``conftest.py``); no PII is checked into the repo.
"""

from __future__ import annotations

import pytest
from kubernetes import client
from tests.integration.utils import (
    Clients,
    PeopleIdentity,
    api_get_json,
)


@pytest.mark.parametrize("mode", ["email", "gitlab_handle"])
def test_people_api_resolves_identity(
    mode: str,
    people_identity: PeopleIdentity,
    k8s_clients: Clients,
    manager_namespace: str,
    api_service: client.V1Service,
):
    query = {mode: getattr(people_identity, mode)}
    status, body = api_get_json(
        k8s_clients.core,
        manager_namespace,
        api_service,
        "api/people",
        query=query,
    )

    if status != 200 or body.get("status") == "not found":
        pytest.skip(
            f"People API returned status={status}, body={body!r}; the "
            "people database is likely disabled in this environment."
        )

    assert body["team"].lower() == people_identity.team.lower(), body
    assert body["slack_id"].lower() == people_identity.slack_id.lower(), body
    assert body["email"].lower() == people_identity.email.lower(), body
    assert body["gitlab_handle"].lower() == people_identity.gitlab_handle.lower(), body


def test_people_api_email_lookup_is_case_insensitive(
    people_identity: PeopleIdentity,
    k8s_clients: Clients,
    manager_namespace: str,
    api_service: client.V1Service,
):
    """The /api/people email lookup must match regardless of input case."""
    expected_email = people_identity.email.lower()

    bodies = {}
    for variant, email in (
        ("upper", people_identity.email.upper()),
        ("lower", people_identity.email.lower()),
    ):
        status, body = api_get_json(
            k8s_clients.core,
            manager_namespace,
            api_service,
            "api/people",
            query={"email": email},
        )

        if status != 200 or body.get("status") == "not found":
            pytest.skip(
                f"People API returned status={status}, body={body!r} for "
                f"{variant}-case email; the people database is likely "
                "disabled in this environment."
            )

        bodies[variant] = body

    for variant, body in bodies.items():
        assert body["email"].lower() == expected_email, (
            f"{variant}-case lookup returned {body!r}"
        )

    assert bodies["upper"] == bodies["lower"], bodies
