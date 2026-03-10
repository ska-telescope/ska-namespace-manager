"""
collect_metrics provides local metrics helpers for collect-controller
replicas.
"""

from prometheus_client import CollectorRegistry, Counter, generate_latest


class CollectMetrics:
    """
    CollectMetrics stores the local collect-controller registry.
    """

    def __init__(self, replica_id: str) -> None:
        self.replica_id = replica_id or "unknown"
        self.registry = CollectorRegistry()
        self.failed_jobs_total = Counter(
            name="namespace_manager_failed_jobs_total",
            documentation="Failed collect task executions",
            labelnames=["replica", "namespace", "job"],
            registry=self.registry,
        )

    def record_failed_job(self, namespace: str, job: str) -> None:
        """
        Increment the failed collect task counter for the namespace/job pair.
        """
        self.failed_jobs_total.labels(
            replica=self.replica_id,
            namespace=namespace,
            job=job,
        ).inc()

    def get_metrics_payload(self) -> bytes:
        """
        Return the current local metrics payload.
        """
        return generate_latest(self.registry)

    @staticmethod
    def merge_payloads(payloads: list[bytes]) -> bytes:
        """
        Merge Prometheus text payloads by de-duplicating metadata lines and
        keeping the individual sample series unchanged.
        """
        lines: list[str] = []
        seen_metadata: set[str] = set()

        for payload in payloads:
            for line in payload.decode("utf-8").splitlines():
                if line == "":
                    continue

                if line.startswith("# HELP") or line.startswith("# TYPE"):
                    if line in seen_metadata:
                        continue

                    seen_metadata.add(line)

                lines.append(line)

        if len(lines) == 0:
            return b""

        return ("\n".join(lines) + "\n").encode("utf-8")
