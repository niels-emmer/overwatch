import hashlib
import math
import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class OutcomeSnapshot:
    success_count: int
    failure_count: int
    timeout_count: int
    abort_count: int
    last_seen_at: datetime | None


def _normalize_command(command: str | None) -> str:
    if not command:
        return ""
    return re.sub(r"\s+", " ", command.strip().lower())


def action_signature(action_type: str, container_name: str, command: str | None) -> str:
    material = f"{action_type}|{container_name.strip().lower()}|{_normalize_command(command)}"
    return hashlib.sha1(material.encode("utf-8")).hexdigest()[:16]


def classify_outcome(result_status: str, output: str | None) -> str:
    if result_status == "done":
        return "success"

    text = (output or "").lower()
    if "timeout" in text:
        return "timeout"
    if "cancel" in text or "abort" in text:
        return "abort"
    return "failure"


def _score(snapshot: OutcomeSnapshot | None, now: datetime) -> tuple[float, str]:
    if snapshot is None:
        return 0.20, "No local history yet"

    total = snapshot.success_count + snapshot.failure_count + snapshot.timeout_count + snapshot.abort_count
    success_rate = (snapshot.success_count + 1) / (total + 2)

    age_hours = 9999.0
    if snapshot.last_seen_at:
        age_hours = max(0.0, (now - snapshot.last_seen_at).total_seconds() / 3600.0)
    recency = math.exp(-age_hours / 72.0)

    failure_penalty = min(
        0.40,
        (snapshot.failure_count * 0.05)
        + (snapshot.timeout_count * 0.07)
        + (snapshot.abort_count * 0.10),
    )

    score = (0.70 * success_rate) + (0.30 * recency) - failure_penalty
    reason = f"{snapshot.success_count}/{total} successful; last seen {int(age_hours) if age_hours < 9999 else 'n/a'}h ago"
    return round(score, 4), reason


def rank_actions(
    actions: list[dict],
    snapshots: dict[str, OutcomeSnapshot],
    now: datetime | None = None,
) -> list[dict]:
    now = now or datetime.utcnow()
    decorated: list[tuple[float, int, dict]] = []

    for idx, action in enumerate(actions):
        signature = action_signature(
            action.get("action_type", ""),
            action.get("container_name", ""),
            action.get("command"),
        )
        snapshot = snapshots.get(signature)
        score, reason = _score(snapshot, now)

        total = 0
        success_rate = None
        if snapshot:
            total = snapshot.success_count + snapshot.failure_count + snapshot.timeout_count + snapshot.abort_count
            if total > 0:
                success_rate = snapshot.success_count / total

        enriched = {
            **action,
            "action_signature": signature,
            "historical_score": score,
            "historical_success_rate": round(success_rate, 3) if success_rate is not None else None,
            "historical_sample_size": total,
            "ranking_reason": reason,
        }
        decorated.append((score, -idx, enriched))

    decorated.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [item[2] for item in decorated]
