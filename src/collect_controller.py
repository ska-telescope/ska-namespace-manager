#!/usr/bin/env python
"""
action_controller provides the execution script for the CollectController
component
"""
import argparse

from ska_ser_namespace_manager.controller.collect_controller import (
    CollectController,
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKA Namespace Manager Collect Controller"
    )
    parser.add_argument(
        "--kubeconfig",
        type=str,
        required=False,
        help="Path to the kubeconfig file",
    )
    args = parser.parse_args()
    CollectController(args.kubeconfig).run()
