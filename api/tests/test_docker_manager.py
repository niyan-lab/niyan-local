from app.services.docker_manager import host_ollama_status, uses_host_ollama_url


def test_host_ollama_url_detects_docker_desktop():
    assert uses_host_ollama_url("http://host.docker.internal:11434")
    assert uses_host_ollama_url("http://127.0.0.1:11434")
    assert uses_host_ollama_url("http://localhost:11434")
    assert not uses_host_ollama_url("http://ollama:11434")
    assert not uses_host_ollama_url("")


def test_host_ollama_status_healthy_when_reachable():
    row = host_ollama_status("http://host.docker.internal:11434", True)
    assert row.name == "ollama"
    assert row.healthy is True
    assert row.status == "host"
    assert row.status != "not_created"


def test_host_ollama_status_unhealthy_when_unreachable():
    row = host_ollama_status("http://host.docker.internal:11434", False)
    assert row.healthy is False
    assert row.status == "unreachable"
