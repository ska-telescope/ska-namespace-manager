"""
ownership_collector gets and adds ownership information to
a namespace
"""

import sys
from typing import Callable, Dict

import requests
from ska_cicd_services_api.people_database_api import PeopleDatabaseUser

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.types import NamespaceAnnotations
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

        labels = namespace.metadata.labels or {}
        annotations = namespace.metadata.annotations or {}
        response = requests.get(
            f"{self.config.people_api.url}/api/people",
            params={
                "gitlab_handle": labels.get("cicd.skao.int/author", ""),
                "email": annotations.get("cicd.skao.int/authorEmail", ""),
            },
            timeout=10,
        )
        if response.status_code != 200:
            logging.error(
                "Failed to retrieve information from People API: %s",
                response.status_code,
            )
            sys.exit(1)
        else:
            user = PeopleDatabaseUser(**response.json())

        self.patch_namespace(
            self.namespace,
            annotations={
                NamespaceAnnotations.OWNER.value: encode_slack_address(
                    name=user.name, slack_id=user.slack_id
                )
            },
        )
        logging.debug(
            "Completed ownership check for namespace: '%s", self.namespace
        )
