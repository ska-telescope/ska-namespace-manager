#!/usr/bin/env python
"""
action_controller provides the execution script for the CollectController
component
"""

from ska_ser_namespace_manager.controller.collect_controller import (
    CollectController,
)

if __name__ == "__main__":
    CollectController().run()
