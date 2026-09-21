"""Tests for system hardware and AI monitor metrics."""

from not3.config import Settings
from not3.system import get_system_metrics


def test_get_system_metrics():
    settings = Settings()
    metrics = get_system_metrics(settings, {"busy": False, "stage": None})

    assert "cpu" in metrics
    assert "percent" in metrics["cpu"]
    assert "cores" in metrics["cpu"]

    assert "memory" in metrics
    assert "percent" in metrics["memory"]

    assert "gpu" in metrics
    assert "available" in metrics["gpu"]

    assert "ai" in metrics
    assert metrics["ai"]["busy"] is False
