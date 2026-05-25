from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass

from fingerprints import normalize_line


_SEVERITY_WEIGHT = {
    "info": 0.0,
    "warning": 0.4,
    "error": 0.8,
    "critical": 1.2,
}


@dataclass(frozen=True)
class AnomalyResult:
    score: float
    reasons: tuple[str, ...]
    suspicious_count: int
    should_emit: bool


class AnomalyScorer:
    def __init__(
        self,
        *,
        anomaly_threshold: float,
        history_windows: int = 10,
        novelty_weight: float = 1.0,
        spike_weight: float = 1.5,
    ):
        self._anomaly_threshold = anomaly_threshold
        self._history: dict[str, deque[int]] = defaultdict(lambda: deque(maxlen=history_windows))
        self._seen_signatures: dict[str, set[str]] = defaultdict(set)
        self._last_eval: dict[str, dict] = {}
        self._novelty_weight = novelty_weight
        self._spike_weight = spike_weight

    def evaluate(
        self,
        *,
        container_name: str,
        threshold: int,
        lines: list[str],
        max_level: str,
    ) -> AnomalyResult:
        suspicious_count = len(lines)
        if suspicious_count == 0:
            return AnomalyResult(score=0.0, reasons=tuple(), suspicious_count=0, should_emit=False)

        history = self._history[container_name]
        baseline = (sum(history) / len(history)) if history else 0.0

        score = 0.0
        reasons: list[str] = []

        normalized = {normalize_line(line) for line in lines if line.strip()}
        unseen = [sig for sig in normalized if sig not in self._seen_signatures[container_name]]
        if unseen:
            score += self._novelty_weight
            reasons.append("novel_fingerprint")

        if baseline > 0 and suspicious_count >= max(threshold, int(baseline * 2)):
            score += self._spike_weight
            reasons.append("rate_spike")

        sev_weight = _SEVERITY_WEIGHT.get(max_level.lower(), 0.0)
        if sev_weight > 0:
            score += sev_weight
            reasons.append(f"severity_{max_level.lower()}")

        threshold_trigger = suspicious_count >= threshold
        anomaly_trigger = score >= self._anomaly_threshold
        should_emit = threshold_trigger or anomaly_trigger

        history.append(suspicious_count)
        self._seen_signatures[container_name].update(normalized)
        self._last_eval[container_name] = {
            "baseline": baseline,
            "suspicious_count": suspicious_count,
            "score": round(score, 3),
            "reasons": reasons,
            "threshold_trigger": threshold_trigger,
            "anomaly_trigger": anomaly_trigger,
        }

        return AnomalyResult(
            score=round(score, 3),
            reasons=tuple(reasons),
            suspicious_count=suspicious_count,
            should_emit=should_emit,
        )

    def snapshot(self, container_name: str | None = None) -> dict:
        if container_name:
            return self._last_eval.get(container_name, {})
        return dict(self._last_eval)
