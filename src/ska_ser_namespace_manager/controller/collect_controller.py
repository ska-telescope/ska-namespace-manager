"""
collect_controller provides the collect controller component. This controller
is responsible for creating tasks to collect information on managed
resources
"""

import datetime
import time
from typing import Optional

import yaml

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
                for action in self.namespace_cronjobs:
                    self.create_collect_cronjob(action, namespace, ns_config)

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

        if len(existing_cronjobs) > 0:
            self.batch_v1.patch_namespaced_cron_job(
                existing_cronjobs[0].metadata.name,
                self.config.context.namespace,
                yaml.safe_load(manifest),
                _request_timeout=10,
            )
            logging.info(
                "Patched '%s' CronJob for namespace '%s'", action, namespace
            )
        else:
            if self.config.prometheus.enabled:
                # Delay for Prometheus to scrape the namespace on first run
                time.sleep(self.config.prometheus.cronjob_delay)
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
        manifest = self.template_factory.render(
            f"{action}-job.j2",
            target_namespace=namespace,
            action=str(action),
            actions=config.actions,
            context=self.config.context,
        )

        existing_jobs = self.get_jobs_by(
            namespace=self.config.context.namespace,
            annotations={
                NamespaceAnnotations.NAMESPACE: namespace,
                NamespaceAnnotations.ACTION: action,
            },
        )

        if len(existing_jobs) > 0:
            self.batch_v1.patch_namespaced_job(
                existing_jobs[0].metadata.name,
                self.config.context.namespace,
                yaml.safe_load(manifest),
                _request_timeout=10,
            )
            logging.info(
                "Patched '%s' Job for namespace '%s'", action, namespace
            )
        else:
            self.batch_v1.create_namespaced_job(
                self.config.context.namespace,
                yaml.safe_load(manifest),
                _request_timeout=10,
            )
            logging.info(
                "Created '%s' Job for namespace '%s'", action, namespace
            )

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
                namespace = job.metadata.annotations.get(
                    NamespaceAnnotations.NAMESPACE
                )
                ns = self.get_namespace(namespace)
                if ns is None:
                    self.batch_v1.delete_namespaced_job(
                        job.metadata.name,
                        self.config.context.namespace,
                        _request_timeout=10,
                    )
                    logging.info(
                        "Deleted '%s' Job for namespace '%s'",
                        action,
                        namespace,
                    )

                    job_pods = self.get_namespace_pods_by(
                        namespace=self.config.context.namespace,
                        labels={
                            "job-name": job.metadata.name,
                        },
                    )

                    for pod in job_pods:
                        self.v1.delete_namespaced_pod(
                            pod.metadata.name,
                            self.config.context.namespace,
                            _request_timeout=10,
                        )
                        logging.info(
                            "Deleted '%s' Pod from Job '%s'"
                            " for namespace '%s'",
                            action,
                            job.metadata.name,
                            namespace,
                        )

                    continue

                ns_config = match_namespace(
                    self.config.namespaces, self.to_dto(ns)
                )
                self.batch_v1.patch_namespaced_job(
                    job.metadata.name,
                    self.config.context.namespace,
                    yaml.safe_load(
                        self.template_factory.render(
                            f"{action}-job.j2",
                            target_namespace=namespace,
                            action=action,
                            actions=ns_config.actions,
                            context=self.config.context,
                        )
                    ),
                    _request_timeout=10,
                )
                logging.debug(
                    "Patched '%s' Job for namespace '%s'", action, namespace
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
