"""Tests for collect-controller configuration defaults and overrides."""

import os
from datetime import timedelta

import pytest

from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectControllerConfig,
)


def test_collect_controller_config_heartbeat_defaults():
    """Collect-controller config should expose heartbeat defaults."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
        }
    )

    assert config.heartbeat.path == "/tmp/collect-controller-heartbeat"
    assert config.heartbeat.max_age_seconds == 60
    assert config.context.stateful_set_name is None


def test_collect_controller_config_heartbeat_overrides():
    """Collect-controller config should honor heartbeat overrides."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
            "heartbeat": {
                "path": "var/run/collect-heartbeat",
                "max_age_seconds": 120,
            },
        }
    )

    assert config.heartbeat.path == os.path.abspath(
        "var/run/collect-heartbeat"
    )
    assert config.heartbeat.max_age_seconds == 120


def test_collect_controller_config_prometheus_datacentre_default():
    """Collect-controller config should default Prometheus datacentre."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
        }
    )

    assert config.prometheus.datacentre is None


def test_collect_controller_config_prometheus_datacentre_override():
    """Collect-controller config should load Prometheus datacentre."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
            "prometheus": {
                "datacentre": "stfc-techops",
            },
        }
    )

    assert config.prometheus.datacentre == "stfc-techops"


def test_collect_controller_config_stateful_set_name():
    """Collect-controller config should load StatefulSet identity."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
                "stateful_set_name": "namespace-manager-collect-controller",
            },
            "leader_election": {
                "enabled": True,
            },
        }
    )

    assert (
        config.context.stateful_set_name
        == "namespace-manager-collect-controller"
    )


def test_collect_controller_config_namespace_check_defaults():
    """Collect-controller namespace config should expose check defaults."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
            "namespaces": [
                {
                    "names": ["ci-.*"],
                },
            ],
        }
    )

    assert config.namespaces[0].checks.cancelled is False
    assert config.namespaces[0].checks.superseded is False


def test_collect_controller_config_namespace_check_overrides():
    """Collect-controller namespace config should load check overrides."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
            "namespaces": [
                {
                    "names": ["ci-.*"],
                    "checks": {
                        "cancelled": True,
                        "superseded": True,
                    },
                },
            ],
        }
    )

    assert config.namespaces[0].checks.cancelled is True
    assert config.namespaces[0].checks.superseded is True


def test_collect_controller_config_gitlab_defaults():
    """Collect-controller config should expose GitLab defaults."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
        }
    )

    assert config.gitlab.enabled is False
    assert config.gitlab.api_base == "https://gitlab.com"
    assert config.gitlab.requester == ""
    assert config.gitlab.private_token is None
    assert config.gitlab.cache_ttl == timedelta(minutes=5)
    assert config.gitlab.cache_max_entries == 10000


def test_collect_controller_config_gitlab_overrides():
    """Collect-controller config should load GitLab overrides."""
    config = CollectControllerConfig.model_validate(
        {
            "context": {
                "namespace": "default",
                "service_account": "collect-ctl-sa",
                "image": "example/image:latest",
                "config_path": "/etc/config",
                "config_secret": "collect-config",
            },
            "leader_election": {
                "enabled": True,
            },
            "gitlab": {
                "enabled": True,
                "api_base": "https://gitlab.example.test",
                "requester": "namespace-manager",
                "private_token": "token",
                "cache_ttl": "10m",
                "cache_max_entries": 500,
            },
        }
    )

    assert config.gitlab.enabled is True
    assert config.gitlab.api_base == "https://gitlab.example.test"
    assert config.gitlab.requester == "namespace-manager"
    assert config.gitlab.private_token == "token"
    assert config.gitlab.cache_ttl == timedelta(minutes=10)
    assert config.gitlab.cache_max_entries == 500


def test_collect_controller_config_gitlab_requires_token_when_enabled():
    """GitLab config should require a private token when enabled."""
    with pytest.raises(ValueError, match="private_token"):
        CollectControllerConfig.model_validate(
            {
                "context": {
                    "namespace": "default",
                    "service_account": "collect-ctl-sa",
                    "image": "example/image:latest",
                    "config_path": "/etc/config",
                    "config_secret": "collect-config",
                },
                "leader_election": {
                    "enabled": True,
                },
                "gitlab": {
                    "enabled": True,
                },
            }
        )
