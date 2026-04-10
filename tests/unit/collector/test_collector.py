"""
Tests for collector action execution helpers.
"""

from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)


class ExampleCollector(Collector):
    """Minimal collector used to test the shared action runner."""

    def __init__(self, namespace, config_class, kubeconfig=None):
        """Store the provided construction details for assertions."""
        Collector.__init__(self, namespace, config_class, kubeconfig)
        self.namespace = namespace
        self.config_class = config_class
        self.kubeconfig = kubeconfig
        self.ran = False

    @classmethod
    def get_actions(cls):
        """Return the supported test actions."""
        return {CollectActions.CHECK_NAMESPACE: cls.check_namespace}

    def check_namespace(self):
        """Record that the action executed."""
        self.ran = True


def test_run_action():
    """Supported actions should instantiate the collector and execute."""
    with patch.object(Collector, "__init__", return_value=None), patch.object(
        ExampleCollector, "check_namespace"
    ) as mock_action:
        ExampleCollector.run_action(
            CollectActions.CHECK_NAMESPACE,
            "test-namespace",
            MagicMock(),
            "/tmp/kubeconfig",
        )

    mock_action.assert_called_once()


def test_run_action_unsupported():
    """Unsupported actions should raise a clear error."""
    with pytest.raises(ValueError):
        ExampleCollector.run_action(
            CollectActions.GET_OWNER_INFO,
            "test-namespace",
            MagicMock(),
        )
