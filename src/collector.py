"""
Entry point for the namespace collector Cronjob which collects
information on namespaces and labels them according to its state.
"""

import argparse
import sys

from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.core.logging import logging

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Namespace Checker")
    parser.add_argument(
        "--action",
        type=str,
        required=True,
        help="Action to perform (e.g., check_namespace)",
    )
    parser.add_argument(
        "--namespace", type=str, required=True, help="Namespace to check"
    )
    parser.add_argument(
        "--kubeconfig_path",
        type=str,
        required=False,
        help="Path to the kubeconfig file",
    )
    args = parser.parse_args()

    method_name = args.action
    target_namespace = args.namespace
    kubeconfig_path = args.kubeconfig_path

    if kubeconfig_path:
        logging.info("Using kubeconfig file at %s", kubeconfig_path)

    logging.info(
        "Running %s for namespace: '%s", method_name, target_namespace
    )

    checker = NamespaceCollector(target_namespace, kubeconfig_path)

    methods = {"check_namespace": checker.check_namespace}

    if method_name not in methods:
        logging.error("Function %s is not defined.", method_name)
        sys.exit()

    logging.info("Calling method %s", method_name)
    methods[method_name]()
