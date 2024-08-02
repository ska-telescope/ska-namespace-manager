"""
ownership_collector gets and adds ownership information to
a namespace
"""

from typing import Callable, Dict

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.utils import encode_slack_address


class OwnershipCollector(Collector):
    """
    OwnershipCollector collects ownership information and adds it to the
    namespace as annotations
    """

    @classmethod
    def get_actions(cls) -> Dict[CollectActions, Callable]:
        """
        Returns the possible actions for this collector

        :return: Dict of actions for this collector
        """
        return {CollectActions.GET_OWNER_INFO: cls.get_owner_info}

    def get_owner_info(self) -> None:
        """
        Gets the owner information and adds details as annotations

        :param annotations: The existing
        :param status: The status to set
        """
        logging.debug(
            "Starting ownership check for namespace '%s'", self.namespace
        )
        namespace = self.get_namespace(self.namespace)
        if namespace is None:
            logging.error("Failed to get namespace '%s'", self.namespace)
            return

        # TODO: Curl the API to actually get the data

        annotations = namespace.metadata.annotations or {}
        annotations["manager.cicd.skao.int/owner"] = encode_slack_address(
            slack_id="U03FF5JBF0U", name="Osório, Pedro"
        )
        self.patch_namespace(self.namespace, annotations=annotations)
        logging.debug(
            "Completed ownership check for namespace: '%s", self.namespace
        )
