"""test_metrics tests API-side metrics aggregation"""

from unittest.mock import MagicMock, patch

from ska_ser_namespace_manager.api.metrics import Metrics
from ska_ser_namespace_manager.core.types import NamespaceAnnotations


def test_get_metrics_uses_cache():
    metrics = Metrics.__new__(Metrics)
    metrics.config = MagicMock()
    metrics.config.cache_ttl = 15
    metrics._cached_metrics = b"cached"
    metrics._cached_at = 100.0

    with patch(
        "ska_ser_namespace_manager.api.metrics.time.time",
        return_value=110.0,
    ):
        assert metrics.get_metrics() == b"cached"


def test_build_metrics_payload_reads_managed_namespaces():
    metrics = Metrics.__new__(Metrics)
    metrics.config = MagicMock()
    metrics.kubernetes_api = MagicMock()
    namespace = MagicMock()
    namespace.metadata.name = "ci-test"
    namespace.metadata.labels = {}
    namespace.metadata.annotations = {
        NamespaceAnnotations.MANAGED.value: "true",
        NamespaceAnnotations.STATUS.value: "ok",
    }
    metrics.kubernetes_api.get_namespaces_by.return_value = [namespace]

    payload = metrics._build_metrics_payload().decode("utf-8")

    assert "namespace_manager_ns_status" in payload
    assert 'namespace="ci-test"' in payload
