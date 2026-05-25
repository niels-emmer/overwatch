from types import SimpleNamespace

import pytest

import ai_analyzer


@pytest.fixture(autouse=True)
def stub_ai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OVERWATCH_AI_STUB", "1")


@pytest.mark.asyncio
async def test_analyze_logs_stub_contract() -> None:
    cfg = SimpleNamespace(
        ollama=SimpleNamespace(
            analysis_model="qwen3:8b",
            planning_model="devstral-small-2",
            host="http://localhost:11434",
        )
    )

    result = await ai_analyzer.analyze_logs(
        container_name="api",
        log_text="ERROR: connection timeout",
        config=cfg,
    )

    assert result is not None
    assert result["severity"] in {"INFO", "WARNING", "ERROR", "CRITICAL"}
    assert isinstance(result["summary"], str)
    assert isinstance(result["root_cause"], str)
    assert isinstance(result["confidence"], float)


@pytest.mark.asyncio
async def test_generate_plan_stub_contract() -> None:
    cfg = SimpleNamespace(
        ollama=SimpleNamespace(
            analysis_model="qwen3:8b",
            planning_model="devstral-small-2",
            host="http://localhost:11434",
        )
    )

    result = await ai_analyzer.generate_plan(
        finding={"severity": "ERROR", "summary": "db timeout", "root_cause": "network"},
        container_name="api",
        config=cfg,
    )

    assert result is not None
    assert isinstance(result["steps"], list)
    assert isinstance(result["proposed_actions"], list)
    assert result["proposed_actions"][0]["container_name"] == "api"
