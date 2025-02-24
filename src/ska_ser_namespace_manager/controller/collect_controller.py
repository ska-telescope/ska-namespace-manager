"""
collect_controller provides the collect controller component. This controller
is responsible for creating tasks to collect information on managed
resources
"""

import datetime
import hashlib
import time
import traceback
from typing import Optional

import yaml
from kubernetes.client.exceptions import ApiException

from ska_ser_namespace_manager.controller.collect_controller_config import (
    CollectActions,
    CollectControllerConfig,
    CollectNamespaceConfig,
)
from ska_ser_namespace_manager.controller.controller import (
    conditional_controller_task,
    controller_task,
)
from ska_ser_namespace_manager.controller.leader_controller import (
    LeaderController,
)
from ska_ser_namespace_manager.core.logging import logging
from ska_ser_namespace_manager.core.namespace import match_namespace
from ska_ser_namespace_manager.core.types import (
    NamespaceAnnotations,
    NamespaceStatus,
)
from ska_ser_namespace_manager.metrics.metrics import MetricsManager


class CollectController(LeaderController):
    """
    CollectController is responsible for creating tasks to collect
    information on managed resources and manage those tasks
    """

    namespace_cronjobs: list[CollectActions]
    namespace_jobs: list[CollectActions]
    metrics_manager: MetricsManager

    def __init__(self, kubeconfig: Optional[str] = None) -> None:
        """
        Initialize the CollectController
        """
        LeaderController.__init__(
            self,
            CollectControllerConfig,
            [self.check_new_namespaces],
            kubeconfig,
        )

        self.config: CollectControllerConfig
        self.metrics_manager = MetricsManager(self.config.metrics)
        logging.debug(
            "Configuration: \n%s",
            yaml.safe_dump(yaml.safe_load(self.config.model_dump_json())),
        )
        self.add_tasks(
            [
                self.synchronize_cronjobs,
                self.synchronize_jobs,
                self.generate_metrics,
            ]
        )

        self.namespace_cronjobs = [CollectActions.CHECK_NAMESPACE]
        self.namespace_jobs = [CollectActions.GET_OWNER_INFO]

    def is_metrics_enabled(self) -> bool:
        """
        Check if metrics are enabled
        """
        return self.config.metrics.enabled

    def wait_for_job_deletion(self, job_name, namespace, timeout):
        """
        Waits until the specified job is completely deleted.

        :param job_name: Name of the Kubernetes Job
        :param namespace: Kubernetes namespace
        :param timeout: Maximum wait time in seconds
        :raises TimeoutError: If the job is not deleted within the timeout
        period
        """
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self.batch_v1.read_namespaced_job(job_name, namespace)
                time.sleep(1)
            except ApiException as e:
                if e.status == 404:
                    logging.info(f"Job {job_name} deleted successfully.")
                    return

                logging.error(
                    f"Error checking job {job_name} in namespace {namespace} while deleting: {e}"  # noqa: E501 pylint: disable=line-too-long
                )
                raise
        raise TimeoutError(
            f"Job {job_name} was not deleted within {timeout} seconds."
        )

    @controller_task(period=datetime.timedelta(seconds=1))
    def check_new_namespaces(self) -> None:
        """
        Check for new namespaces and create collection jobs
        """
        unmanaged_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                exclude_annotations={
                    NamespaceAnnotations.MANAGED.value: "true"
                }
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]

        for namespace in unmanaged_namespaces:
            ns_config = match_namespace(
                self.config.namespaces, self.to_dto(namespace)
            )
            if ns_config:
                namespace = namespace.metadata.name
                logging.info(
                    "Managing new namespace '%s'",
                    namespace,
                )
                try:
                    for action in self.namespace_cronjobs:
                        self.create_collect_cronjob(
                            action, namespace, ns_config
                        )

                    for action in self.namespace_jobs:
                        self.create_collect_job(action, namespace, ns_config)

                    self.patch_namespace(
                        namespace,
                        annotations={
                            NamespaceAnnotations.STATUS: NamespaceStatus.UNKNOWN.value,  # pylint: disable=line-too-long  # noqa: E501
                            NamespaceAnnotations.MANAGED: "true",
                            NamespaceAnnotations.NAMESPACE: namespace,
                        },
                    )
                except (  # pylint: disable=broad-exception-caught
                    Exception
                ) as exc:
                    logging.error(
                        "Error while managing new namespace '%s': %s\n%s",
                        namespace,
                        str(exc),
                        traceback.format_exc(),
                    )

    def create_collect_cronjob(
        self,
        action: CollectActions,
        namespace: str,
        config: CollectNamespaceConfig,
    ) -> None:
        """
        Create a new CronJob for the given namespace to actively collect
        namespace information

        :param action: Action to run in the cronjob
        :param namespace: The namespace to create the CronJob for
        :param config: Config governing this namespace collection configuration
        """
        manifest = self.template_factory.render(
            f"{action}-cronjob.j2",
            target_namespace=namespace,
            action=str(action),
            actions=config.actions,
            context=self.config.context,
        )
        existing_cronjobs = self.get_cronjobs_by(
            namespace=self.config.context.namespace,
            annotations={
                NamespaceAnnotations.NAMESPACE: namespace,
                NamespaceAnnotations.ACTION: action,
            },
        )
        if existing_cronjobs:
            for job in existing_cronjobs:
                self.batch_v1.patch_namespaced_cron_job(
                    job.metadata.name,
                    self.config.context.namespace,
                    yaml.safe_load(manifest),
                    _request_timeout=10,
                )
                logging.info(
                    "Patched '%s' CronJob for namespace '%s'",
                    action,
                    namespace,
                )
        else:
            self.batch_v1.create_namespaced_cron_job(
                self.config.context.namespace,
                yaml.safe_load(manifest),
                _request_timeout=10,
            )
            logging.info(
                "Created '%s' CronJob for namespace '%s'", action, namespace
            )

    @conditional_controller_task(
        period=datetime.timedelta(milliseconds=10000),
        run_if=LeaderController.is_leader,
    )
    def synchronize_cronjobs(self) -> None:
        """
        Synchronize created cronjobs by patching or deleting them
        """
        for action in self.namespace_cronjobs:
            cronjobs = self.get_cronjobs_by(
                namespace=self.config.context.namespace,
                annotations={
                    NamespaceAnnotations.ACTION: action,
                },
            )
            for cronjob in cronjobs:
                try:
                    namespace = cronjob.metadata.annotations.get(
                        NamespaceAnnotations.NAMESPACE
                    )
                    ns = self.get_namespace(namespace)
                    if ns is None:
                        self.batch_v1.delete_namespaced_cron_job(
                            cronjob.metadata.name,
                            self.config.context.namespace,
                            _request_timeout=10,
                        )
                        logging.info(
                            "Deleted '%s' CronJob for namespace '%s'",
                            action,
                            namespace,
                        )
                        continue

                    ns_config = match_namespace(
                        self.config.namespaces, self.to_dto(ns)
                    )
                    self.batch_v1.patch_namespaced_cron_job(
                        cronjob.metadata.name,
                        self.config.context.namespace,
                        yaml.safe_load(
                            self.template_factory.render(
                                f"{action}-cronjob.j2",
                                target_namespace=namespace,
                                action=str(action),
                                actions=ns_config.actions,
                                context=self.config.context,
                            )
                        ),
                        _request_timeout=10,
                    )
                    logging.debug(
                        "Patched '%s' CronJob for namespace '%s'",
                        action,
                        namespace,
                    )
                except (  # pylint: disable=broad-exception-caught
                    Exception
                ) as exc:
                    logging.error(
                        "Error while synchronizing '%s' cronjob for '%s': %s\n%s",  # pylint: disable=line-too-long  # noqa: E501
                        action,
                        namespace,
                        str(exc),
                        traceback.format_exc(),
                    )

    def create_collect_job(
        self,
        action: CollectActions,
        namespace: str,
        config: CollectNamespaceConfig,
    ) -> None:
        """
        Create a new Job for the given namespace to collect
        namespace information

        :param namespace: The namespace to create the CronJob for
        :param config: Config governing this namespace collection configuration
        """
        existing_jobs = self.get_jobs_by(
            namespace=self.config.context.namespace,
            annotations={
                NamespaceAnnotations.NAMESPACE: namespace,
                NamespaceAnnotations.ACTION: action,
            },
        )
        if existing_jobs:
            for job in existing_jobs:
                self.batch_v1.delete_namespaced_job(
                    job.metadata.name,
                    self.config.context.namespace,
                    propagation_policy="Background",
                    _request_timeout=10,
                )
                self.wait_for_job_deletion(
                    job.metadata.name,
                    self.config.context.namespace,
                    timeout=10,
                )
                logging.info(
                    "Deleted '%s' Job for namespace '%s'", action, namespace
                )

        manifest = self.template_factory.render(
            f"{action}-job.j2",
            target_namespace=namespace,
            action=str(action),
            actions=config.actions,
            context=self.config.context,
        )
        spec_hash = hashlib.sha256(manifest.encode()).hexdigest()[:8]
        manifest_dict = yaml.safe_load(manifest)
        manifest_dict["metadata"]["annotations"][
            NamespaceAnnotations.SPEC_HASH
        ] = spec_hash
        self.batch_v1.create_namespaced_job(
            self.config.context.namespace,
            manifest_dict,
            _request_timeout=10,
        )
        logging.info("Created '%s' Job for namespace '%s'", action, namespace)

    @conditional_controller_task(
        period=datetime.timedelta(milliseconds=10000),
        run_if=LeaderController.is_leader,
    )
    def synchronize_jobs(self) -> None:
        """
        Synchronize created jobs by patching or deleting them
        """
        for action in self.namespace_jobs:
            jobs = self.get_jobs_by(
                namespace=self.config.context.namespace,
                annotations={
                    NamespaceAnnotations.ACTION: action,
                },
            )
            for job in jobs:
                try:
                    namespace = job.metadata.annotations.get(
                        NamespaceAnnotations.NAMESPACE
                    )
                    ns = self.get_namespace(namespace)
                    if ns is None:
                        self.batch_v1.delete_namespaced_job(
                            job.metadata.name,
                            self.config.context.namespace,
                            propagation_policy="Background",
                            _request_timeout=10,
                        )
                        logging.info(
                            "Deleted '%s' Job for namespace '%s'",
                            action,
                            namespace,
                        )

                        continue

                    current_spec_hash = job.metadata.annotations.get(
                        NamespaceAnnotations.SPEC_HASH
                    )
                    ns_config = match_namespace(
                        self.config.namespaces, self.to_dto(ns)
                    )
                    manifest = self.template_factory.render(
                        f"{action}-job.j2",
                        target_namespace=namespace,
                        action=action,
                        actions=ns_config.actions,
                        context=self.config.context,
                    )
                    spec_hash = hashlib.sha256(manifest.encode()).hexdigest()[
                        :8
                    ]
                    if spec_hash != current_spec_hash:
                        self.batch_v1.delete_namespaced_job(
                            job.metadata.name,
                            self.config.context.namespace,
                            propagation_policy="Background",
                            _request_timeout=10,
                        )
                        self.wait_for_job_deletion(
                            job.metadata.name,
                            self.config.context.namespace,
                            timeout=10,
                        )
                        manifest_dict = yaml.safe_load(manifest)
                        manifest_dict["metadata"]["annotations"][
                            NamespaceAnnotations.SPEC_HASH
                        ] = spec_hash
                        self.batch_v1.create_namespaced_job(
                            self.config.context.namespace,
                            manifest_dict,
                            _request_timeout=10,
                        )
                        logging.debug(
                            "Created '%s' Job for namespace '%s'",
                            action,
                            namespace,
                        )
                except (  # pylint: disable=broad-exception-caught
                    Exception
                ) as exc:
                    logging.error(
                        "Error while synchronizing '%s' job for '%s': %s\n%s",
                        action,
                        namespace,
                        str(exc),
                        traceback.format_exc(),
                    )

    @conditional_controller_task(
        period=datetime.timedelta(seconds=5),
        run_if=lambda instance: LeaderController.is_leader(instance)
        and instance.is_metrics_enabled(),
    )
    def generate_metrics(self) -> None:
        """
        Generates metrics on the managed namespaces
        """
        managed_namespaces = [
            namespace
            for namespace in self.get_namespaces_by(
                annotations={NamespaceAnnotations.MANAGED.value: "true"}
            )
            if namespace.metadata.name not in self.forbidden_namespaces
        ]
        self.metrics_manager.delete_stale_metrics(
            [ns.metadata.name for ns in managed_namespaces]
        )

        for ns in managed_namespaces:
            self.metrics_manager.update_namespace_metrics(ns)

        self.metrics_manager.save_metrics()
