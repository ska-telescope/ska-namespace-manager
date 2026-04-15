"""Tests for collect-controller configuration defaults and overrides."""

import os

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
