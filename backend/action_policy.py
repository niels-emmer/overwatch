from __future__ import annotations

import re
from dataclasses import dataclass


_HIGH_RISK_PATTERNS = [
    re.compile(r"\brm\s+-rf\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if="),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
]


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    risk: str
    reason: str


def classify_risk(action_type: str, command: str | None) -> str:
    if action_type == "docker_restart":
        return "low"

    if action_type != "docker_exec":
        return "high"

    cmd = (command or "").strip().lower()
    if not cmd:
        return "high"

    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.search(cmd):
            return "high"

    if any(token in cmd for token in ["chmod", "chown", "sed -i", "kill "]):
        return "medium"

    return "low"


def evaluate_policy(action_type: str, command: str | None, *, high_risk_approved: bool) -> PolicyDecision:
    risk = classify_risk(action_type, command)

    if risk == "high" and not high_risk_approved:
        return PolicyDecision(
            allowed=False,
            risk=risk,
            reason="HIGH_RISK_APPROVAL_REQUIRED",
        )

    return PolicyDecision(allowed=True, risk=risk, reason="allowed")
