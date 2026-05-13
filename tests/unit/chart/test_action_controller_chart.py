"""
Tests for action-controller chart metrics wiring.
"""

from pathlib import Path


def test_action_controller_mounts_metrics_volume_when_enabled():
    """
    Action controller deployment should mount the shared metrics PVC.
    """
    chart_root = Path("charts/ska-ser-namespace-manager")
    deployment_template = (
        chart_root / "templates/action-controller/deployment.yml"
    ).read_text(encoding="utf-8")

    assert "{{- if $appConfig.metrics.enabled }}" in deployment_template
    assert "name: metrics-volume" in deployment_template
    assert "mountPath: {{ $appConfig.metrics.registry_path }}" in (
        deployment_template
    )
    assert (
        'claimName: {{ include "ska-ser-namespace-manager.name" . }}-metrics-registry'  # pylint: disable=line-too-long # noqa: E501
        in deployment_template
    )
