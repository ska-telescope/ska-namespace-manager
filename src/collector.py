"""
collector is an entry point to run collection tasks to gather
information on namespaces and labels them according to its state.
"""

import argparse
import sys

from ska_ser_namespace_manager.collector.collector_config import (
    CollectorConfig,
)
from ska_ser_namespace_manager.collector.namespace_collector import (
    NamespaceCollector,
)
from ska_ser_namespace_manager.collector.ownership_collector import (
    OwnershipCollector,
)
from ska_ser_namespace_manager.core.logging import logging

ACTIONS = {
    **{
        action: NamespaceCollector
        for action in NamespaceCollector.get_actions()
    },
    **{
        action: OwnershipCollector
        for action in OwnershipCollector.get_actions()
    },
}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="SKA Namespace Manager Collector"
    )
    parser.add_argument(
        "--action",
        type=str,
        required=True,
        help=f"Action to perform (one of: {ACTIONS.keys()})",
    )
    parser.add_argument(
        "--namespace",
        type=str,
        required=True,
        help="Namespace to collect information about",
    )
    parser.add_argument(
        "--kubeconfig",
        type=str,
        required=False,
        help="Path to the kubeconfig file",
    )
    args = parser.parse_args()

    action = args.action
    namespace = args.namespace
    kubeconfig = args.kubeconfig

    if action not in ACTIONS:
        logging.error("Can't run undefined action '%s'", action)
        sys.exit(1)

    if kubeconfig:
        logging.info("Using kubeconfig at %s", kubeconfig)

    logging.info("Running '%s' for namespace '%s'", action, namespace)

    collector_class: NamespaceCollector = ACTIONS[action]
    namespace_collector = collector_class(
        namespace, CollectorConfig, kubeconfig
    )
    collector_class.get_actions()[action](namespace_collector)
