"""
namespace_collector checks Kubernetes namespaces
for staleness and failures
"""

import traceback
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

import pytz
from dateutil.parser import parse
from humanfriendly import format_timespan
from kubernetes.client import V1Namespace

from ska_ser_namespace_manager.collector.collector import Collector
from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.types import NamespaceAnnotations
from ska_ser_namespace_manager.core.utils import format_utc, utc


class NamespaceCollector(Collector):
    """
    NamespaceCollector checks namespaces for staleness and failures
    periodically. The inferred status is stored in the form of
    annotations in the namespace itself
    """

    @classmethod
    def get_actions(cls) -> Dict[CollectActions, Callable]:
        """
        Returns the possible actions for this collector

        :return: Dict of actions for this collector
        """
        return {CollectActions.CHECK_NAMESPACE: cls.check_namespace}

    def set_status(
        self,
        namespace: V1Namespace,
        status: str,
        status_annotations: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Set the status and status timestamp in the annotations.

        :param status_annotations: Extra annotations to set on status change
        :param status: The status to set
        """
        annotations = status_annotations or {}
        old_status = (namespace.metadata.annotations or {}).get(
            NamespaceAnnotations.STATUS.value
        )
        if old_status == status:
            return

        annotations[NamespaceAnnotations.STATUS.value] = status
        annotations[NamespaceAnnotations.STATUS_TS.value] = utc()
        annotations[NamespaceAnnotations.NOTIFIED_TS.value] = None
        annotations[NamespaceAnnotations.NOTIFIED_STATUS.value] = None
        logging.info(
            "Setting namespace '%s' status: %s",
            self.namespace,
            status,
        )
        self.patch_namespace(self.namespace, annotations=annotations)

    def check_namespace(self) -> None:
        """
        Check the namespace for staleness and failures.
        """
        logging.info("Starting check for namespace '%s'", self.namespace)
        namespace = self.get_namespace(self.namespace)
        if namespace is None:
            logging.error("Failed to get namespace '%s'", self.namespace)
            return

        running = not (
            self.check_stale(namespace) or self.check_failure(namespace)
        )

        if running:
            self.set_status(namespace, "ok")

        logging.debug("Completed check for namespace: '%s", self.namespace)

    def check_stale(self, namespace: V1Namespace) -> bool:
        """
        Check if the namespace is stale based on the TTL

        :param namespace: Namespace to check
        :return: True if namespace was stale, False otherwise
        """
        if self.namespace_config.ttl is None:
            return False

        creation_timestamp = namespace.metadata.creation_timestamp.replace(
            tzinfo=timezone.utc
        )
        is_stale_ttl = (
            datetime.now(pytz.UTC) - creation_timestamp
            >= self.namespace_config.ttl
        )
        stale_detail = format_timespan(self.namespace_config.ttl)
        is_stale_duplicate: False
        if self.namespace_config.duplicate:
            # TODO: search for duplicates
            # match the labels and annotations
            # it has been created afterwards
            ns_labels = namespace.metadata.labels or {}
            ns_annotations = namespace.metadata.annotations or {}
            ns_matches = self.get_namespaces_by(
                labels={
                    label: ns_labels.get(label, "unknown")
                    for label in (self.namespace_config.duplicate.labels or {})
                },
                annotations={
                    annotation: ns_annotations.get(annotation, "unknown")
                    for annotation in (
                        self.namespace_config.duplicate.annotations or {}
                    )
                },
            )

            for ns_match in ns_matches:
                ns_creation_timestamp = (
                    ns_match.metadata.creation_timestamp.replace(
                        tzinfo=timezone.utc
                    )
                )
                if ns_creation_timestamp > creation_timestamp:
                    is_stale_duplicate = True
                    stale_detail = f"duplicate of {ns_match.metadata.name}"
                    break

        is_stale = is_stale_ttl or is_stale_duplicate
        if is_stale:
            self.set_status(
                namespace,
                "stale",
                {
                    NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(
                        creation_timestamp + self.namespace_config.ttl
                    ),
                    NamespaceAnnotations.STATUS_DETAIL.value: stale_detail,
                },
            )

        return is_stale

    def check_failure(self, namespace: V1Namespace) -> bool:
        """
        Check if there are failures in Deployment, StatefulSet,
        or ReplicaSet and manage status annotations.

        :param namespace: Namespace to check
        :return: True if there are failures, False otherwise.
        """
        annotations = namespace.metadata.annotations or {}
        old_failing_resources = set(
            filter(
                None,
                annotations.get(
                    NamespaceAnnotations.FAILING_RESOURCES.value, ""
                ).split(","),
            )
        )

        deployments = self._check_resource_status(self.namespace, "deployment")
        statefulsets = self._check_resource_status(
            self.namespace, "statefulset"
        )
        replicasets = self._check_resource_status(self.namespace, "replicaset")
        new_failing_resources = set(deployments + statefulsets + replicasets)
        status_timestamp = parse(
            annotations.get(NamespaceAnnotations.STATUS_TS.value, utc())
        ).replace(tzinfo=pytz.UTC)
        new_annotations = {
            NamespaceAnnotations.FAILING_RESOURCES.value: ",".join(
                new_failing_resources
            ),
            NamespaceAnnotations.STATUS_FINALIZE_AT.value: format_utc(
                status_timestamp + self.namespace_config.grace_period
            ),
            NamespaceAnnotations.STATUS_DETAIL.value: format_timespan(
                self.namespace_config.grace_period
            ),
        }

        if old_failing_resources.intersection(
            new_failing_resources
        ) and self._is_after_grace_period(annotations):
            self.set_status(namespace, "failed", new_annotations)
        elif old_failing_resources.intersection(
            new_failing_resources
        ) and not self._is_after_grace_period(annotations):
            self.set_status(namespace, "failing", new_annotations)
        elif (
            new_failing_resources
            and not old_failing_resources
            and not self._is_after_grace_period(annotations)
        ):
            self.set_status(namespace, "failing", new_annotations)
        elif new_failing_resources and old_failing_resources:
            self.set_status(namespace, "unstable", annotations)

        return len(new_failing_resources) > 0

    def _is_after_grace_period(self, annotations: Dict[str, str]) -> bool:
        status_timestamp = parse(
            annotations.get(NamespaceAnnotations.STATUS_TS.value, utc())
        ).replace(tzinfo=None)
        grace_time = status_timestamp + self.namespace_config.grace_period
        logging.debug(
            "Status Timestamp: %s; Grace Timestamp: %s",
            status_timestamp,
            grace_time,
        )
        return datetime.now() > grace_time

    def _check_resource_status(
        self, namespace: str, resource_type: str
    ) -> List[str]:
        """
        Check if any resources of the given type in the specified namespace
        have errors.

        :param namespace: The namespace to check.
        :param resource_type: The type of resource to check
        ('deployment', 'statefulset', 'replicaset').
        :return: List of names of failing resources.
        """
        failing_resources = []

        try:
            if resource_type == "deployment":
                res = self.apps_v1.list_namespaced_deployment(
                    namespace, _request_timeout=10
                )
            elif resource_type == "statefulset":
                res = self.apps_v1.list_namespaced_stateful_set(
                    namespace, _request_timeout=10
                )
            elif resource_type == "replicaset":
                res = self.apps_v1.list_namespaced_replica_set(
                    namespace, _request_timeout=10
                )
            else:
                raise ValueError(f"Unsupported resource type: {resource_type}")

            for resource in res.items:
                available_replicas = resource.status.available_replicas or 0
                desired_replicas = resource.status.replicas or 0
                if available_replicas < desired_replicas:
                    failing_resources.append(resource.metadata.name)
                    logging.warning(
                        "Namespace %s has a %s %s which has "
                        "less replicas than desired.",
                        namespace,
                        resource_type,
                        resource.metadata.name,
                    )

        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.error(
                "Exception when retrieving %s: %s", resource_type, exc
            )
            traceback.print_exception(exc)

        return failing_resources
