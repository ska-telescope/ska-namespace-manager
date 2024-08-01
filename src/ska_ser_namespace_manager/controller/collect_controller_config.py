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

    def __str__(self):
        return self.value


class CollectTaskConfig(BaseModel):
    """
    CollectTaskConfig holds the configurations for the collect controller
    tasks. Properties below are the ones we can set for cronjobs or jobs in
    the Kubernetes API
    """

    schedule: Optional[str] = "*/1 * * * *"
    successful_jobs_history_limit: Optional[int] = 1
    failed_jobs_history_limit: Optional[int] = 3
    concurrency_policy: Optional[str] = "Forbid"


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
        if self.actions is None:
            self.actions = {
                CollectActions.CHECK_NAMESPACE: CollectTaskConfig()
            }


class CollectConfig(BaseModel):
    """
    CollectConfig holds the configurations governing collection of
    information
    """

    namespaces: Optional[List[CollectNamespaceConfig]] = None

    def model_post_init(self, _):
        if self.namespaces is None:
            self.namespaces = []


class CollectControllerConfig(CollectConfig, LeaderControllerConfig):
    """
    CollectControllerConfig provides the configurations for the collect
    controller
    """
