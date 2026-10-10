"""Unit tests for host resource metric helpers."""

from __future__ import annotations

from app.services import host_metrics


def test_parse_nvidia_smi_csv():
    out = "0, NVIDIA GeForce RTX 4090, 42, 8192, 24576\n"
    devices = host_metrics._parse_nvidia_smi(out)
    assert len(devices) == 1
    d = devices[0]
    assert d["index"] == 0
    assert d["name"] == "NVIDIA GeForce RTX 4090"
    assert d["utilization_percent"] == 42.0
    assert d["memory_used_bytes"] == 8192 * 1024 * 1024
    assert d["memory_total_bytes"] == 24576 * 1024 * 1024
    assert d["memory_percent"] == round((8192 / 24576) * 100, 1)


def test_collect_resources_cpu_memory_shape():
    snap = host_metrics.collect_resources()
    assert "cpu" in snap and "memory" in snap and "gpu" in snap
    assert "generated_at" in snap
    assert isinstance(snap["cpu"].get("available"), bool)
    assert isinstance(snap["memory"].get("available"), bool)
    assert isinstance(snap["gpu"]["available"], bool)
    assert isinstance(snap["gpu"]["devices"], list)
    # When psutil is installed, CPU/memory should be available.
    try:
        import psutil  # noqa: F401

        assert snap["cpu"]["available"] is True
        assert snap["memory"]["available"] is True
        assert snap["cpu"]["percent"] is not None
        assert snap["memory"]["percent"] is not None
    except ImportError:
        assert snap["cpu"]["available"] is False


def test_gpu_unavailable_on_kubernetes(monkeypatch):
    # Guard reads the resolved platform; patch the symbol host_metrics imported.
    monkeypatch.setattr(host_metrics, "resolve_platform", lambda: "kubernetes")
    gpu = host_metrics._gpu()
    assert gpu["available"] is False
    assert gpu["devices"] == []
    assert "Kubernetes" in gpu["detail"]
