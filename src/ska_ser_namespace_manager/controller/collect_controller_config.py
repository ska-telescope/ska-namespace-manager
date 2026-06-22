"""
collect_controller_config centralizes all the configuration loading
for the collect controller component
"""

import datetime
import os
import tempfile
from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, BeforeValidator

from ska_ser_namespace_manager.controller.controller_config import (
    KubernetesContext,
)
from ska_ser_namespace_manager.controller.leader_controller_config import (
    LeaderControllerConfig,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import NamespaceMatcher
from ska_ser_namespace_manager.core.utils import parse_timedelta
from ska_ser_namespace_manager.metrics.metrics_config import MetricsConfig


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
    tasks. The schedule uses interval syntax for in-process namespace checks.
    """

    schedule: Optional[str] = "60s"


class CheckOptions(BaseModel):
    """
    CheckOptions holds optional namespace lifecycle checks.

    * cancelled: Whether to check originating GitLab pipeline status
    * superseded: Whether to check older deployments for the same CI identity
    """

    cancelled: bool = False
    superseded: bool = False


class CollectNamespaceConfig(NamespaceMatcher):
    """
    CollectNamespaceConfig holds the configurations indicating how to
    dictate namespace phases.

    * ttl: Namespace ttl to become stale
    * settling_period: Period to mark unstable namespace as failing
    * grace_period: Grace period to mark a failing namespace as failed
    * checks: Optional namespace lifecycle checks
    """

    ttl: Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None = None
    settling_period: (
        Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None
    ) = datetime.timedelta(minutes=5)
    grace_period: (
        Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] | None
    ) = datetime.timedelta(minutes=1)
    checks: CheckOptions = CheckOptions()
    actions: Optional[Dict[CollectActions, CollectTaskConfig]] = None

    def model_post_init(self, _):
        default_actions = {action: CollectTaskConfig() for action in CollectActions}
        if self.actions is None:
            self.actions = default_actions
        else:
            for action in CollectActions:
                self.actions[action] = CollectTaskConfig(
                    **{
                        **CollectTaskConfig().model_dump(),
                        **self.actions.get(action, CollectTaskConfig()).model_dump(),
                    }
                )


class PeopleAPIConfig(BaseModel):
    """
    PeopleAPIConfig holds configurations to govern how we call the
    people api

    * url: URL for the people API
    * ca: CA certificate of the people API
    * ca_path: Path to the CA certificate file
    * insecure: True to ignore the SSL certificate
    """

    url: Optional[str] = "http://localhost:8080"
    ca: Optional[str] = None
    ca_path: Optional[str] = None
    insecure: Optional[bool] = False

    def model_post_init(self, _):
        if not self.insecure and self.ca:
            with tempfile.NamedTemporaryFile(
                prefix="people-api-ca-cert-",
                delete=False,
            ) as cafile:
                cafile.write(self.ca.encode("utf-8"))
                self.ca_path = cafile.name
                logging.info("People API CA Certificate written to '%s'", self.ca_path)


class PrometheusConfig(BaseModel):
    """
    Holds configurations for Prometheus and certificate handling.

    * url: URL for Prometheus
    * ca: CA certificate of Prometheus
    * ca_path: Path to the CA certificate file
    * insecure: True to ignore the SSL certificate
    * datacentre: Optional alert label filter for Prometheus alerts
    """

    url: Optional[str] = None
    ca: Optional[str] = None
    ca_path: Optional[str] = None
    insecure: Optional[bool] = False
    datacentre: Optional[str] = None
    enabled: Optional[bool] = True
    whitelisted_alerts: Optional[list] = []

    def model_post_init(self, _):
        if not self.insecure and self.ca:
            with tempfile.NamedTemporaryFile(
                prefix="prometheus-ca-cert-", delete=False
            ) as cafile:
                cafile.write(self.ca.encode("utf-8"))
                self.ca_path = cafile.name
                logging.info("Prometheus CA Certificate written to '%s'", self.ca_path)


class GitLabConfig(BaseModel):
    """
    GitLabConfig holds configuration for GitLab pipeline status lookups.

    * enabled: True to query GitLab for originating pipeline status
    * api_base: GitLab instance base URL
    * requester: GitLab API requester identity
    * private_token: GitLab private token
    * cache_ttl: Time to cache pipeline status responses
    * cache_max_entries: Maximum cached pipeline statuses
    * request_timeout: Per-request deadline for GitLab API calls
    """

    enabled: Optional[bool] = False
    api_base: Optional[str] = "https://gitlab.com"
    requester: Optional[str] = ""
    private_token: Optional[str] = None
    cache_ttl: Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] = (
        datetime.timedelta(minutes=5)
    )
    cache_max_entries: int = 10000
    request_timeout: Annotated[datetime.timedelta, BeforeValidator(parse_timedelta)] = (
        datetime.timedelta(seconds=10)
    )

    def model_post_init(self, _):
        if self.enabled and not self.private_token:
            raise ValueError(
                "GitLab private_token must be configured when GitLab "
                "pipeline checks are enabled"
            )


class CollectConfig(BaseModel):
    """
    CollectConfig holds the configurations governing collection of
    information
    """

    namespaces: Optional[List[CollectNamespaceConfig]] = None
    people_api: PeopleAPIConfig = PeopleAPIConfig()
    prometheus: PrometheusConfig = PrometheusConfig()
    gitlab: GitLabConfig = GitLabConfig()

    def model_post_init(self, _):
        if self.namespaces is None:
            self.namespaces = []


class HeartbeatConfig(BaseModel):
    """
    HeartbeatConfig holds configurations for the collect-controller
    liveness heartbeat file.
    """

    path: str = "/tmp/collect-controller-heartbeat"
    max_age_seconds: int = 60

    def model_post_init(self, _):
        self.path = os.path.abspath(self.path)


class CollectControllerContext(KubernetesContext):
    """
    CollectControllerContext holds collect-controller runtime identity.
    """

    stateful_set_name: Optional[str] = None


class CollectControllerConfig(CollectConfig, LeaderControllerConfig):
    """
    CollectControllerConfig provides the configurations for the collect
    controller
    """

    context: CollectControllerContext
    heartbeat: HeartbeatConfig = HeartbeatConfig()
    metrics: Optional[MetricsConfig] = MetricsConfig()
