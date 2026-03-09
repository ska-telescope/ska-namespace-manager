"""test_collector tests collector bootstrapping behavior"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.collector.collector_config import CollectorConfig
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectNamespaceConfig,
)


@pytest.fixture
def collector_config():
    config = MagicMock(spec=CollectorConfig)
    config.prometheus = MagicMock()
    config.namespaces = []
    return config


def test_collector_uses_default_namespace_config(collector_config):
    namespace_resource = MagicMock()

    with patch(
        "ska_ser_namespace_manager.collector.collector.KubernetesAPI.__init__",
        return_value=None,
    ), patch(
        "ska_ser_namespace_manager.collector.collector.ConfigLoader"
    ) as mock_config_loader, patch.object(
        Collector, "get_namespace", return_value=namespace_resource
    ), patch.object(
        Collector, "to_dto", return_value=MagicMock()
    ), patch(
        "ska_ser_namespace_manager.collector.collector.match_namespace",
        return_value=None,
    ):
        mock_config_loader.return_value.load.return_value = collector_config

        collector = Collector("ci-test", CollectorConfig)

    assert collector.namespace == "ci-test"
    assert isinstance(collector.namespace_config, CollectNamespaceConfig)
    assert collector.namespace_config.settling_period == timedelta(minutes=5)


def test_collector_exits_when_namespace_missing(collector_config):
    with patch(
        "ska_ser_namespace_manager.collector.collector.KubernetesAPI.__init__",
        return_value=None,
    ), patch(
        "ska_ser_namespace_manager.collector.collector.ConfigLoader"
    ) as mock_config_loader, patch.object(
        Collector, "get_namespace", return_value=None
    ), patch(
        "ska_ser_namespace_manager.collector.collector.sys.exit"
    ) as mock_exit:
        mock_config_loader.return_value.load.return_value = collector_config

        Collector("ci-missing", CollectorConfig)

    mock_exit.assert_called_once_with(1)
