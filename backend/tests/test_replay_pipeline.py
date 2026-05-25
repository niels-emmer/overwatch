import json
from pathlib import Path

from replay import ReplayLine, detect_findings_from_lines


FIXTURE = Path(__file__).parent / "fixtures" / "replay" / "suspicious-window.json"


def test_replay_fixture_produces_finding() -> None:
    payload = json.loads(FIXTURE.read_text())
    lines = [ReplayLine(ts=item["ts"], text=item["text"]) for item in payload]

    findings = detect_findings_from_lines(
        lines,
        window_seconds=30,
        min_error_lines_to_trigger=3,
    )

    assert len(findings) == 1
    assert len(findings[0].suspicious_lines) == 3


def test_replay_ignores_noise() -> None:
    lines = [
        ReplayLine(ts=0, text="INFO healthy"),
        ReplayLine(ts=2, text="debug trace"),
        ReplayLine(ts=5, text="all good"),
    ]
    findings = detect_findings_from_lines(
        lines,
        window_seconds=30,
        min_error_lines_to_trigger=3,
    )
    assert findings == []
