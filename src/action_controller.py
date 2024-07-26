#!/usr/bin/env python
"""
action_controller provides the execution script for the ActionController
component
"""

from ska_ser_namespace_manager.controller.action_controller import (
    ActionController,
)

if __name__ == "__main__":
    ActionController().run()
