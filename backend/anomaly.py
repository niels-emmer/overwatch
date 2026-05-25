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
    risk_score: float
    risk_horizon_minutes: int
    reasons: tuple[str, ...]
    suspicious_count: int
    baseline: float
    drift_ratio: float
    should_emit: bool


class AnomalyScorer:
    def __init__(
        self,
        *,
        anomaly_threshold: float,
        risk_threshold: float = 65.0,
        history_windows: int = 10,
        novelty_weight: float = 1.0,
        spike_weight: float = 1.5,
    ):
        self._anomaly_threshold = anomaly_threshold
        self._risk_threshold = risk_threshold
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
            return AnomalyResult(
                score=0.0,
                risk_score=0.0,
                risk_horizon_minutes=120,
                reasons=tuple(),
                suspicious_count=0,
                baseline=0.0,
                drift_ratio=0.0,
                should_emit=False,
            )

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

        drift_ratio = 0.0
        if baseline > 0:
            drift_ratio = suspicious_count / baseline
        if drift_ratio >= 1.5:
            reasons.append("baseline_drift")

        load_ratio = min(1.5, suspicious_count / max(1, threshold))
        normalized_anomaly = min(1.0, score / max(0.1, self._anomaly_threshold))
        normalized_drift = min(1.0, drift_ratio / 3.0)
        normalized_load = min(1.0, load_ratio / 1.5)
        risk_score = ((0.5 * normalized_anomaly) + (0.3 * normalized_drift) + (0.2 * normalized_load)) * 100.0

        if risk_score >= 85:
            horizon = 15
        elif risk_score >= 70:
            horizon = 30
        elif risk_score >= 55:
            horizon = 60
        else:
            horizon = 120

        threshold_trigger = suspicious_count >= threshold
        anomaly_trigger = score >= self._anomaly_threshold
        risk_trigger = risk_score >= self._risk_threshold
        if risk_trigger and "risk_score_high" not in reasons:
            reasons.append("risk_score_high")
        should_emit = threshold_trigger or anomaly_trigger or risk_trigger

        history.append(suspicious_count)
        self._seen_signatures[container_name].update(normalized)
        self._last_eval[container_name] = {
            "baseline": baseline,
            "suspicious_count": suspicious_count,
            "score": round(score, 3),
            "risk_score": round(risk_score, 2),
            "risk_horizon_minutes": horizon,
            "drift_ratio": round(drift_ratio, 3),
            "reasons": reasons,
            "threshold_trigger": threshold_trigger,
            "anomaly_trigger": anomaly_trigger,
            "risk_trigger": risk_trigger,
        }

        return AnomalyResult(
            score=round(score, 3),
            risk_score=round(risk_score, 2),
            risk_horizon_minutes=horizon,
            reasons=tuple(reasons),
            suspicious_count=suspicious_count,
            baseline=round(baseline, 3),
            drift_ratio=round(drift_ratio, 3),
            should_emit=should_emit,
        )

    def snapshot(self, container_name: str | None = None) -> dict:
        if container_name:
            return self._last_eval.get(container_name, {})
        return dict(self._last_eval)
