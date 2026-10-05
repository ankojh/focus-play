"""Tests never inherit the operator's live LLM activation/profile."""
import os
import pytest


@pytest.fixture(autouse=True)
def isolated_llm_environment(monkeypatch):
    for name in os.environ:
        if name.startswith(("LLM_", "OLLAMA_")):
            monkeypatch.delenv(name)
    # Existing transport mocks remain explicit Ollama rollback regressions.
    monkeypatch.setenv("OLLAMA_MODEL", "gemma4:12b-mlx")
