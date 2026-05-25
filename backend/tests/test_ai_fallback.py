import os

import pytest

import ai_analyzer


@pytest.mark.asyncio
async def test_fallback_routes_when_primary_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERWATCH_ANALYSIS_FALLBACK_MODELS", "backup-model")

    calls: list[str] = []

    async def fake_chat(model: str, system: str, user: str, host: str):
        calls.append(model)
        if model == "primary-model":
            return None
        return '{"severity":"ERROR","summary":"ok","root_cause":"r","confidence":0.9}'

    monkeypatch.setattr(ai_analyzer, "_chat", fake_chat)

    result = await ai_analyzer._chat_with_fallback(
        "primary-model",
        "sys",
        "user",
        "http://localhost:11434",
        kind="analysis",
    )

    assert result is not None
    assert calls == ["primary-model", "backup-model"]


def test_health_snapshot_contains_runtime_fields() -> None:
    snap = ai_analyzer.ai_health_snapshot()

    assert "max_concurrency" in snap
    assert "models" in snap
    assert "circuit_fail_threshold" in snap
