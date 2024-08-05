"""
collect_controller_config centralizes all the configuration loading
for the collect controller component
"""

import datetime
from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator

from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)
from ska_ser_namespace_manager.core.namespace import NamespaceMatcher
from ska_ser_namespace_manager.core.utils import parse_timedelta


class CollectActions(str, Enum):
    """
    CollectActions describes all known collection actions
    """

    CHECK_NAMESPACE = "check-namespace"
    GET_OWNER_INFO = "get-owner-info"

    def __str__(self):
        return self.value


class CollectTaskConfig(BaseModel):
    """
    CollectTaskConfig holds the configurations for the collect controller
    tasks. Properties below are the ones we can set for cronjobs or jobs in
    the Kubernetes API
    """

    schedule: Optional[str] = "*/1 * * * *"
    successful_jobs_history_limit: Optional[int] = None
    failed_jobs_history_limit: Optional[int] = None
    concurrency_policy: Optional[str] = "Forbid"
    active_deadline_seconds: Optional[int] = None
    backoff_limit: Optional[int] = None
    parallelism: Optional[int] = None


class CollectNamespaceConfig(NamespaceMatcher):
    """
    CollectNamespaceConfig holds the configurations indicating how to
    dictate namespace phases.

    * ttl: Namespace ttl to become stale
    * grace_period: Grace period to mark a failing namespace as failed
    """

    ttl: (
        Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None
    ) = None
    grace_period: (
        Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None
    ) = datetime.timedelta(minutes=1)
    actions: Optional[Dict[CollectActions, CollectTaskConfig]] = None

    def model_post_init(self, _):
        default_actions = {
            action: CollectTaskConfig() for action in CollectActions
        }
        if self.actions is None:
            self.actions = default_actions
        else:
            for action in CollectActions:
                self.actions[action] = CollectTaskConfig(
                    **{
                        **CollectTaskConfig().model_dump(),
                        **self.actions.get(
                            action, CollectTaskConfig()
                        ).model_dump(),
                    }
                )


class PeopleAPIConfig(BaseModel):
    """
    PeopleAPIConfig holds configurations to govern how we call the
    people api

    * url: URL for the people API
    """

    url: Optional[str] = "http://localhost:8080"


class CollectConfig(BaseModel):
    """
    CollectConfig holds the configurations governing collection of
    information
    """

    namespaces: Optional[List[CollectNamespaceConfig]] = None
    people_api: PeopleAPIConfig = PeopleAPIConfig()

    def model_post_init(self, _):
        if self.namespaces is None:
            self.namespaces = []


class CollectControllerConfig(CollectConfig, LeaderControllerConfig):
    """
    CollectControllerConfig provides the configurations for the collect
    controller
    """
