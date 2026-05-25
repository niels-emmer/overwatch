from __future__ import annotations

ACTIVE_STATUSES = {"open", "investigating", "mitigated", "regressed"}

_ALLOWED_TRANSITIONS = {
    "open": {"investigating", "mitigated", "resolved", "dismissed"},
    "investigating": {"mitigated", "resolved", "dismissed"},
    "mitigated": {"resolved", "regressed", "dismissed"},
    "regressed": {"investigating", "mitigated", "resolved", "dismissed"},
    "resolved": {"regressed", "dismissed"},
    "dismissed": set(),
}


def is_valid_transition(current: str, target: str) -> bool:
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def status_after_successful_action(current: str) -> str | None:
    if current in ACTIVE_STATUSES:
        return "mitigated"
    return None


def status_for_regression(current: str) -> str | None:
    if current in {"mitigated", "resolved"}:
        return "regressed"
    return None
