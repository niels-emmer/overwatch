from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from error_detector import is_suspicious


@dataclass(frozen=True)
class ReplayLine:
    ts: float
    text: str


@dataclass(frozen=True)
class ReplayFinding:
    first_ts: float
    last_ts: float
    suspicious_lines: tuple[str, ...]


def detect_findings_from_lines(
    lines: Iterable[ReplayLine],
    *,
    window_seconds: int,
    min_error_lines_to_trigger: int,
) -> list[ReplayFinding]:
    findings: list[ReplayFinding] = []
    window: list[ReplayLine] = []

    for line in lines:
        if not is_suspicious(line.text):
            continue

        window.append(line)
        cutoff = line.ts - window_seconds
        window = [w for w in window if w.ts >= cutoff]

        if len(window) >= min_error_lines_to_trigger:
            findings.append(
                ReplayFinding(
                    first_ts=window[0].ts,
                    last_ts=window[-1].ts,
                    suspicious_lines=tuple(w.text for w in window),
                )
            )
            window = []

    return findings
