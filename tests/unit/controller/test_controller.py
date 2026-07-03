"""
Tests for generic controller and thread-manager behavior.
"""

import datetime
import signal
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.controller import (
    Controller,
    conditional_controller_task,
    controller_task,
)


@pytest.fixture(name="mock_kubernetes_api", autouse=True)
def mock_kubernetes_api_fixture():
    """Provide a mocked Kubernetes API for controller tests."""
    with (
        patch(
            "ska_ser_namespace_manager.controller.controller.KubernetesAPI",
            autospec=True,
        ) as mock_api_class,
        patch(
            "ska_ser_namespace_manager.core.kubernetes_api.config.load_kube_config",  # pylint: disable=line-too-long # noqa: E501
            new_callable=MagicMock(),
        ),
        patch(
            "ska_ser_namespace_manager.core.kubernetes_api.config.load_incluster_config",  # pylint: disable=line-too-long # noqa: E501
            new_callable=MagicMock(),
        ),
    ):
        mock_api_instance = mock_api_class.return_value
        mock_api_instance.v1 = MagicMock()

        yield mock_api_instance


@pytest.fixture(name="controller")
def controller_fixture():
    """Build a controller instance with mocked config loading."""
    mock_config_class = MagicMock()
    mock_config_instance = MagicMock()
    mock_config_class.return_value = mock_config_instance
    mock_config_instance.context.namespace = "default-namespace"

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = mock_config_instance
        controller_instance = Controller(config_class=mock_config_class, tasks=[])
        yield controller_instance


def test_add_tasks(controller):
    """Static tasks should be registered without starting immediately."""

    def dummy_task():
        """No-op task used for registration tests."""
        return None

    controller.add_tasks([dummy_task])
    assert len(controller.threads) == 1
    assert controller.threads["dummy_task"].name == "dummy_task"


def test_terminate(controller):
    """Terminating the controller should set the shutdown event."""
    stop_event = threading.Event()
    controller.task_stop_events["managed-task"] = stop_event

    controller.terminate()

    assert controller.shutdown_event.is_set()
    assert stop_event.is_set()


@patch("ska_ser_namespace_manager.controller.controller.logging.debug")
def test_run_controller(_mock_logging_debug, controller):
    """Running the controller should start registered threads once."""

    def dummy_task():
        """No-op task used for thread start tests."""
        return None

    controller.add_tasks([dummy_task])

    with patch(
        "ska_ser_namespace_manager.core.thread_manager.threading.Thread.start"  # pylint: disable=line-too-long # noqa: E501
    ) as mock_thread_start:
        controller.cleanup = MagicMock()
        controller.run()
        assert mock_thread_start.call_count == 1
        controller.cleanup.assert_called_once()


def test_add_managed_task_after_run(controller):
    """Managed tasks should start immediately after the controller runs."""
    task_calls = []

    def managed_task(stop_event):
        """Record the stop event passed into the managed task."""
        task_calls.append(stop_event)

    controller.run(blocking=False)
    controller.add_managed_task("managed-task", managed_task)

    controller.threads["managed-task"].join()

    assert len(task_calls) == 1
    assert controller.task_stop_events["managed-task"] is task_calls[0]


def test_remove_task_stops_single_managed_task(controller):
    """Removing a task should stop its thread without stopping others."""
    stopped = threading.Event()

    def managed_task(stop_event):
        """Run until asked to stop, then flag completion."""
        while not stop_event.is_set():
            time.sleep(0.01)
        stopped.set()

    controller.add_managed_task("managed-task", managed_task)
    controller.run(blocking=False)
    controller.remove_task("managed-task")

    assert stopped.wait(timeout=1)
    assert "managed-task" not in controller.threads


def test_cleanup_stops_managed_tasks(controller):
    """Cleanup should stop managed tasks via the controller shutdown path."""
    stopped = threading.Event()

    def managed_task(stop_event):
        """Run until the task or controller requests shutdown."""
        while not stop_event.is_set() and not controller.shutdown_event.is_set():
            time.sleep(0.01)
        stopped.set()

    controller.add_managed_task("managed-task", managed_task)
    controller.run(blocking=False)
    controller.cleanup()

    assert stopped.wait(timeout=1)


def test_wait_for_task_stop_times_out_without_stop(controller):
    """Waiting should time out when neither stop condition is triggered."""
    stop_event = threading.Event()

    assert not controller.wait_for_task_stop(stop_event, 0.05)


def test_wait_for_task_stop_wakes_on_task_stop(controller):
    """Waiting should end promptly when the managed stop event is set."""
    stop_event = threading.Event()
    controller.task_stop_events["managed-task"] = stop_event
    waiter_done = threading.Event()
    result = {}

    def waiter():
        result["stopped"] = controller.wait_for_task_stop(stop_event, 5)
        waiter_done.set()

    wait_thread = threading.Thread(target=waiter)
    wait_thread.start()
    time.sleep(0.05)
    controller.remove_task("managed-task")

    assert waiter_done.wait(timeout=1)
    wait_thread.join()
    assert result["stopped"] is True


def test_wait_for_task_stop_wakes_on_terminate(controller):
    """Waiting should end promptly when the controller is terminated."""
    stop_event = threading.Event()
    controller.task_stop_events["managed-task"] = stop_event
    waiter_done = threading.Event()
    result = {}

    def waiter():
        result["stopped"] = controller.wait_for_task_stop(stop_event, 5)
        waiter_done.set()

    wait_thread = threading.Thread(target=waiter)
    wait_thread.start()
    time.sleep(0.05)
    controller.terminate()

    assert waiter_done.wait(timeout=1)
    wait_thread.join()
    assert result["stopped"] is True
    assert stop_event.is_set()


def test_shutdown_signal_terminates_managed_tasks(controller):
    """Signal shutdown should apply full terminate semantics."""
    stop_event = threading.Event()
    controller.task_stop_events["managed-task"] = stop_event

    with patch.object(controller, "terminate") as mock_terminate:
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)

    mock_terminate.assert_called_once()


def test_controller_task_decorator():
    """Controller tasks should loop until shutdown and log failures."""
    mock_config = MagicMock()
    mock_config.context.namespace = "default-namespace"

    class TestController(Controller):
        """Controller variant used to test periodic task execution."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.task_call_count = 0

        @controller_task(period=datetime.timedelta(milliseconds=10))
        def decorated_task(self):
            """Increment the counter on each scheduled run."""
            self.task_call_count += 1

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = mock_config
        test_controller = TestController(config_class=dict, tasks=[])

    # Start the decorated task in a separate thread
    task_thread = threading.Thread(target=test_controller.decorated_task)
    task_thread.start()

    # Allow some time for the task to be executed
    time.sleep(0.1)

    # Stop the Controller
    test_controller.shutdown_event.set()
    task_thread.join()

    # Verify that the task was called multiple times
    assert test_controller.task_call_count > 1

    # Testing exception handling
    class FaultyController(Controller):
        """Controller variant used to verify exception logging."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @controller_task(period=datetime.timedelta(milliseconds=10))
        def faulty_task(self):
            """Raise an exception on every scheduled run."""
            raise ValueError("Test Exception")

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = mock_config
        faulty_controller = FaultyController(config_class=dict, tasks=[])

    with patch(
        "ska_ser_namespace_manager.controller.controller.logging.error"
    ) as mock_logging_error:
        task_thread = threading.Thread(target=faulty_controller.faulty_task)
        task_thread.start()

        time.sleep(0.1)
        faulty_controller.shutdown_event.set()
        task_thread.join()

    assert mock_logging_error.call_count > 0


def test_conditional_controller_task_decorator():
    """Conditional controller tasks should respect the condition."""
    mock_config = MagicMock()
    mock_config.context.namespace = "default-namespace"

    class TestController(Controller):
        """Controller variant used to test conditional execution."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.conditional_task_call_count = 0

        @conditional_controller_task(
            period=datetime.timedelta(milliseconds=10),
            run_if=lambda ctrl: ctrl.config.context.namespace == "default-namespace",
        )
        def conditional_task(self):
            """Increment the counter when the condition is true."""
            self.conditional_task_call_count += 1

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = mock_config
        test_controller = TestController(config_class=dict, tasks=[])

    # Start the conditional task in a separate thread
    task_thread = threading.Thread(target=test_controller.conditional_task)
    task_thread.start()

    # Run for a short time and then set shutdown_event to stop
    time.sleep(0.05)
    test_controller.shutdown_event.set()
    task_thread.join()

    assert test_controller.conditional_task_call_count > 0

    # Testing exception handling
    class FaultyController(Controller):
        """Controller variant used to test conditional error logging."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @conditional_controller_task(
            period=datetime.timedelta(milliseconds=10),
            run_if=lambda ctrl: ctrl.config.context.namespace == "default-namespace",
        )
        def faulty_task(self):
            """Raise an exception when the condition is true."""
            raise ValueError("Test Exception")

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = mock_config
        faulty_controller = FaultyController(config_class=dict, tasks=[])

    with patch(
        "ska_ser_namespace_manager.controller.controller.logging.error"
    ) as mock_logging_error:
        task_thread = threading.Thread(target=faulty_controller.faulty_task)
        task_thread.start()

        time.sleep(0.1)
        faulty_controller.shutdown_event.set()
        task_thread.join()

        # Check if the exception was logged
    assert mock_logging_error.call_count > 0

    # Test condition where the task should not run
    class ConditionalFalseController(Controller):
        """Controller variant used to verify skipped execution."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.conditional_task_call_count = 0

        @conditional_controller_task(
            period=datetime.timedelta(milliseconds=10),
            run_if=lambda ctrl: ctrl.config.context.namespace == "wrong-namespace",
        )
        def conditional_task(self):
            """Increment the counter when the condition is true."""
            self.conditional_task_call_count += 1

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = mock_config
        false_controller = ConditionalFalseController(config_class=dict, tasks=[])

    task_thread = threading.Thread(target=false_controller.conditional_task)
    task_thread.start()

    time.sleep(0.05)
    false_controller.shutdown_event.set()
    task_thread.join()

    assert false_controller.conditional_task_call_count == 0
