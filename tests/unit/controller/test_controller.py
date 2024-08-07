import datetime
import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from ska_ser_namespace_manager.controller.controller import (
    Controller,
    conditional_controller_task,
    controller_task,
)


@pytest.fixture
def mock_kubernetes_api():
    with patch(
        "ska_ser_namespace_manager.controller.controller.KubernetesAPI",
        autospec=True,
    ) as mock_api_class, patch(
        "ska_ser_namespace_manager.core.kubernetes_api.config.load_kube_config",  # pylint: disable=line-too-long # noqa: E501
        new_callable=MagicMock(),
    ), patch(
        "ska_ser_namespace_manager.core.kubernetes_api.config.load_incluster_config",  # pylint: disable=line-too-long # noqa: E501
        new_callable=MagicMock(),
    ):
        mock_api_instance = mock_api_class.return_value
        mock_api_instance.v1 = MagicMock()

        yield mock_api_instance


@pytest.fixture
def controller(mock_kubernetes_api):
    mock_config_class = MagicMock()
    mock_config_instance = MagicMock()
    mock_config_class.return_value = mock_config_instance
    mock_config_instance.context.namespace = "default-namespace"

    with patch(
        "ska_ser_namespace_manager.controller.controller.ConfigLoader"
    ) as mock_config_loader:
        mock_config_loader.return_value.load.return_value = (
            mock_config_instance
        )
        controller_instance = Controller(
            config_class=mock_config_class, tasks=[]
        )
        yield controller_instance


def test_add_tasks(controller):
    def dummy_task():
        pass

    controller.add_tasks([dummy_task])
    assert len(controller.threads) == 1
    assert controller.threads["dummy_task"]._target == dummy_task


def test_terminate(controller):
    controller.terminate()
    assert controller.shutdown_event.is_set()


@patch("ska_ser_namespace_manager.controller.controller.logging.debug")
def test_run_controller(mock_logging_debug, controller):
    def dummy_task():
        pass

    controller.add_tasks([dummy_task])

    with patch(
        "ska_ser_namespace_manager.core.thread_manager.threading.Thread.start"  # pylint: disable=line-too-long # noqa: E501
    ) as mock_thread_start:
        controller.cleanup = MagicMock()
        controller.run()
        assert mock_thread_start.call_count == 1
        controller.cleanup.assert_called_once()


def test_controller_task_decorator(controller):
    class TestController(Controller):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.task_call_count = 0

        @controller_task(period=datetime.timedelta(milliseconds=10))
        def decorated_task(self):
            self.task_call_count += 1

    test_controller = TestController(config_class=MagicMock(), tasks=[])

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
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @controller_task(period=datetime.timedelta(milliseconds=10))
        def faulty_task(self):
            raise ValueError("Test Exception")

    faulty_controller = FaultyController(config_class=MagicMock(), tasks=[])

    with patch(
        "ska_ser_namespace_manager.controller.controller.logging.error"
    ) as mock_logging_error:
        task_thread = threading.Thread(target=faulty_controller.faulty_task)
        task_thread.start()

        time.sleep(0.1)
        faulty_controller.shutdown_event.set()
        task_thread.join()

        assert mock_logging_error.call_count > 0


def test_conditional_controller_task_decorator(controller):
    class TestController(Controller):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.conditional_task_call_count = 0

        @conditional_controller_task(
            period=datetime.timedelta(milliseconds=10),
            run_if=lambda ctrl: ctrl.config.context.namespace
            == "default-namespace",
        )
        def conditional_task(self):
            self.conditional_task_call_count += 1

    test_controller = TestController(config_class=MagicMock(), tasks=[])

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
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @conditional_controller_task(
            period=datetime.timedelta(milliseconds=10),
            run_if=lambda ctrl: ctrl.config.context.namespace
            == "default-namespace",
        )
        def faulty_task(self):
            raise ValueError("Test Exception")

    faulty_controller = FaultyController(config_class=MagicMock(), tasks=[])

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
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.conditional_task_call_count = 0

        @conditional_controller_task(
            period=datetime.timedelta(milliseconds=10),
            run_if=lambda ctrl: ctrl.config.context.namespace
            == "wrong-namespace",
        )
        def conditional_task(self):
            self.conditional_task_call_count += 1

    false_controller = ConditionalFalseController(
        config_class=MagicMock(), tasks=[]
    )

    task_thread = threading.Thread(target=false_controller.conditional_task)
    task_thread.start()

    time.sleep(0.05)
    false_controller.shutdown_event.set()
    task_thread.join()

    assert false_controller.conditional_task_call_count == 0
