"""
collect_controller provides the collect controller component. This controller
is responsible for creating tasks to collect information on managed
resources
"""

import datetime
from typing import List, Optional

import prometheus_client
import yaml
from kubernetes import client

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


class CollectController(LeaderController, MetricsManager):
    """
    CollectController is responsible for creating tasks to collect
    information on managed resources and manage those tasks
    """

    namespace_cronjobs: list[CollectActions]
    namespace_jobs: list[CollectActions]

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
        MetricsManager.__init__(self, CollectControllerConfig)

        self.config: CollectControllerConfig
        logging.debug(
            "Configuration: \n%s",
            yaml.safe_dump(yaml.safe_load(self.config.model_dump_json())),
        )
        self.add_tasks(
            [
                self.synchronize_cronjobs,
                self.synchronize_jobs,
                self.list_namespaces_and_export_metrics,
            ]
        )

        self.namespace_cronjobs = [CollectActions.CHECK_NAMESPACE]
        self.namespace_jobs = [CollectActions.GET_OWNER_INFO]

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

    def delete_stale_gauge(
        self,
        gauge: prometheus_client.Metric,
        namespaces: List[client.V1Namespace],
        value: int = -1,
    ):
        """
        Delete gauge if the corresponding namespace is not longer active
        """
        active_namespaces = {ns.metadata.name for ns in namespaces}
        for sample in gauge._samples():  # pylint: disable=protected-access
            if sample.labels.get("namespace") not in active_namespaces:
                gauge.labels(**sample.labels).set(value)

    @conditional_controller_task(
        period=datetime.timedelta(seconds=5),
        run_if=lambda instance: LeaderController.is_leader(instance)
        and instance.config.metrics.enabled,
    )
    def list_namespaces_and_export_metrics(self) -> None:
        """
        List namespaces in the Kubernetes cluster and export Prometheus
        metrics based on their labels and annotations.
        """
        namespaces = self.v1.list_namespace().items

        self.delete_stale_gauge(self.namespace_manager_ns_status, namespaces)
        self.delete_stale_gauge(
            self.namespace_cpu_usage_millicores, namespaces, value=0
        )
        self.delete_stale_gauge(
            self.namespace_memory_usage_megabytes, namespaces, value=0
        )

        for ns in namespaces:
            labels = ns.metadata.labels or {}
            annotations = ns.metadata.annotations or {}

            author = labels.get("cicd.skao.int/author", "unknown")
            team = labels.get("cicd.skao.int/team", "unknown")
            project = labels.get("cicd.skao.int/project", "unknown")
            environment = labels.get(
                "cicd.skao.int/environmentTier", "unknown"
            )
            status = annotations.get("manager.cicd.skao.int/status", "unknown")
            status_numeric = NamespaceStatus.from_string(status).value_numeric

            logging.debug(
                f"Namespace '{ns.metadata.name}' fetched with "
                f"labels: {labels} and annotations: {annotations}"
            )
            self.namespace_manager_ns_status.labels(
                team=team,
                project=project,
                user=author,
                environment=environment,
                namespace=ns.metadata.name,
            ).set(status_numeric)

            logging.debug(
                f"Updated metrics for namespace '{ns.metadata.name}' - "
                f"Team: {team}, Project: {project}, User: {author}, "
                f"Environment: {environment}, Status: {status}"
            )

            resource_usage = self.get_namespace_resource_usage(
                ns.metadata.name
            )

            cpu_usage_millicores = resource_usage.get("cpu")
            memory_usage_megabytes = resource_usage.get("memory")

            self.namespace_cpu_usage_millicores.labels(
                team=team,
                project=project,
                user=author,
                environment=environment,
                namespace=ns.metadata.name,
            ).set(cpu_usage_millicores)

            logging.debug(
                f"Updated CPU usage for namespace '{ns.metadata.name}' - "
                f"Environment: {environment}, "
                f"CPU Usage (millicores): {cpu_usage_millicores}"
            )

            self.namespace_memory_usage_megabytes.labels(
                team=team,
                project=project,
                user=author,
                environment=environment,
                namespace=ns.metadata.name,
            ).set(memory_usage_megabytes)

            logging.debug(
                f"Updated Memory usage for namespace '{ns.metadata.name}' - "
                f"Environment: {environment}, "
                f"Memory Usage (MB): {memory_usage_megabytes}"
            )

        self.save_metrics()
