import json
from pathlib import Path

import httpx
import pytest

from app.config import Settings, TURBO_MODEL
from app.errors import AppError
from app.llm.identity import LaunchIdentity, file_identity
from app.llm.turbofieldfare import TurboFieldfare
from app.providers import Ollama, create_model


@pytest.fixture(autouse=True)
def clean_llm_env(monkeypatch):
    import os
    for key in os.environ:
        if key.startswith(("LLM_", "OLLAMA_")): monkeypatch.delenv(key)


def test_fresh_default_and_legacy_precedence(tmp_path, monkeypatch):
    settings = Settings(data=tmp_path)
    assert isinstance(create_model(settings), TurboFieldfare)
    assert settings.model == TURBO_MODEL and settings.context == 16384
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b-mlx")
    settings = Settings(data=tmp_path)
    assert isinstance(create_model(settings), Ollama)
    monkeypatch.setenv("LLM_PROVIDER", "turbofieldfare")
    settings = Settings(data=tmp_path)
    assert settings.model == TURBO_MODEL
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "gemma4:26b")
    monkeypatch.setenv("LLM_MAX_OUTPUT_TOKENS", "2400")
    assert Settings(data=tmp_path).model == "gemma4:26b"
    assert Settings(data=tmp_path).predict == 2400


@pytest.mark.parametrize("url", ["https://127.0.0.1:8080/v1", "http://example.com:8080/v1", "http://127.0.0.1/v1",
    "http://user@127.0.0.1:8080/v1", "http://127.0.0.1:0/v1", "http://127.0.0.1:8080/v1/v1",
    "http://127.0.0.1:8080/v1?q=1", "http://127.0.0.1:8080/v1#secret", "http://127.0.0.1:8080"])
def test_local_url_rejections(tmp_path, url):
    with pytest.raises(ValueError): Settings(data=tmp_path, base_url=url)


@pytest.mark.parametrize("url", ["http://127.0.0.1:8080/v1", "http://localhost:8081/v1/", "http://[::1]:8080/v1"])
def test_loopback_urls(tmp_path, url):
    assert Settings(data=tmp_path, base_url=url).base_url == url.rstrip("/")


@pytest.mark.parametrize("kwargs", [{"provider": "cloud"}, {"model": "qwen3:8b"}, {"predict": 5000}, {"attempt_timeout": 0},
                                      {"task_timeout": 0}, {"task_timeout": 121},
                                      {"first_playable_timeout": 0}, {"first_playable_timeout": 241}])
def test_invalid_config_fails_before_requests(tmp_path, kwargs):
    with pytest.raises(ValueError): Settings(data=tmp_path, **kwargs)


def test_health_endpoints_no_generation_and_fingerprint_identity(tmp_path, monkeypatch):
    requested = []
    real = httpx.Client
    def handle(request):
        requested.append(request.url.path)
        if request.url.path == "/health": return httpx.Response(200, json={"status": "ok", "vision": "missing"})
        return httpx.Response(200, json={"data": [{"id": TURBO_MODEL}]})
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handle), **kw))
    model = create_model(Settings(data=tmp_path))
    monkeypatch.setattr(model.identity, "verify", lambda: {"manifest_sha256": "verified", "runtime_binary_sha256": "build"})
    fingerprint = model.fingerprint()
    assert requested == ["/health", "/v1/models"]
    assert fingerprint["provider"] == "turbofieldfare"
    assert "digest" not in fingerprint and "think" not in fingerprint
    assert fingerprint["capabilities"]["json_schema"] is False
    assert fingerprint["runtime_binary_sha256"] == "build"
    monkeypatch.setattr(model.identity, "verify", lambda: {"manifest_sha256": "verified", "runtime_binary_sha256": "other"})
    assert model.fingerprint() != fingerprint


@pytest.mark.parametrize("reply", [None, {"data": []}, {"data": [{"id": "wrong"}]}, {"data": "bad"}])
def test_health_malformed_or_redirect_never_falls_back(tmp_path, monkeypatch, reply):
    real = httpx.Client
    def handle(request):
        if reply is None: return httpx.Response(302, headers={"location": "http://remote.invalid/"})
        return httpx.Response(200, json={"status": "ok"} if request.url.path == "/health" else reply)
    monkeypatch.setattr(httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handle), **kw))
    with pytest.raises(AppError): create_model(Settings(data=tmp_path)).readiness()


def test_receipt_detects_process_port_and_file_changes(tmp_path, monkeypatch):
    from app.llm import identity
    binary = tmp_path / "binary"; binary.write_bytes(b"existing build")
    receipt = tmp_path / "receipt.json"
    body = {"version": 1, "base_url": "http://127.0.0.1:8080/v1", "model": TURBO_MODEL,
            "profile": {"max_context": 16384}, "pid": 123, "process_identity": "started /binary --model /model",
            "files": {str(binary): file_identity(binary)}, "fingerprint": {"runtime_binary_sha256": "hash"}}
    receipt.write_text(json.dumps(body))
    settings = Settings(data=tmp_path, identity_receipt=receipt)
    check = LaunchIdentity(settings)
    monkeypatch.setattr(identity, "process_identity", lambda pid: body["process_identity"])
    monkeypatch.setattr(identity, "listening", lambda pid, port: True)
    assert check.verify() == body["fingerprint"]
    binary.write_bytes(b"different build")
    with pytest.raises(AppError): check.verify()
    body["files"] = {str(binary): file_identity(binary)}; receipt.write_text(json.dumps(body))
    monkeypatch.setattr(identity, "listening", lambda pid, port: False)
    with pytest.raises(AppError): check.verify()
    monkeypatch.setattr(identity, "listening", lambda pid, port: True)
    monkeypatch.setattr(identity, "process_identity", lambda pid: "different process reusing PID")
    with pytest.raises(AppError): check.verify()
