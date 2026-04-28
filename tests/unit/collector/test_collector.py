"""
Tests for collector action execution helpers.
"""

from unittest.mock import MagicMock, patch

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)


class ExampleCollector(Collector):
    """Minimal collector used to test the shared action runner."""

    def __init__(self, config_class, kubeconfig=None):
        """Store the provided construction details for assertions."""
        Collector.__init__(self, config_class, kubeconfig)
        self.config_class = config_class
        self.kubeconfig = kubeconfig
        self.ran = False

    @classmethod
    def get_actions(cls):
        """Return the supported test actions."""
        return {CollectActions.CHECK_NAMESPACE: cls.check_namespace}

    def check_namespace(self, _namespace, _namespace_resource):
        """Record that the action executed."""
        self.ran = True


def test_run_action():
    """Supported actions should execute on an existing collector."""
    collector = ExampleCollector.__new__(ExampleCollector)
    collector.get_namespace = MagicMock(return_value=MagicMock())

    with patch.object(ExampleCollector, "check_namespace") as mock_action:
        collector.run_action(
            CollectActions.CHECK_NAMESPACE,
            "test-namespace",
        )

    collector.get_namespace.assert_called_once_with("test-namespace")
    mock_action.assert_called_once()
