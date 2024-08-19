#!/usr/bin/env python
"""
action_controller provides the execution script for the ActionController
component
"""
import argparse

from ska_ser_namespace_manager.controller.action_controller import (
    ActionController,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKA Namespace Manager Action Controller"
    )
    parser.add_argument(
        "--kubeconfig",
        type=str,
        required=False,
        help="Path to the kubeconfig file",
    )
    args = parser.parse_args()
    ActionController(args.kubeconfig).run()
