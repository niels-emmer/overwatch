from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CorrelationResult:
    incident_group: str
    confidence: float
    evidence: list[str]
    blast_radius: list[str]


def stack_prefix(container_name: str) -> str:
    parts = container_name.split("-")
    if parts:
        return parts[0]
    return container_name


def _new_group(container_name: str, fingerprint: str) -> str:
    seed = f"{stack_prefix(container_name)}:{fingerprint[:12]}"
    return f"inc-{hashlib.sha1(seed.encode('utf-8')).hexdigest()[:10]}"


def correlate_incident(
    *,
    container_name: str,
    fingerprint: str,
    trigger_reasons: list[str],
    peer_containers: list[str],
    candidate_groups: list[tuple[str, str, datetime | None]],
) -> CorrelationResult:
    evidence: list[str] = []
    confidence = 0.45

    current_stack = stack_prefix(container_name)
    grouped = None

    for group_id, other_container, _ in candidate_groups:
        if stack_prefix(other_container) == current_stack:
            grouped = group_id
            evidence.append(f"same_stack:{current_stack}")
            confidence += 0.25
            break

    if "rate_spike" in trigger_reasons:
        evidence.append("rate_spike")
        confidence += 0.10
    if "novel_fingerprint" in trigger_reasons:
        evidence.append("novel_fingerprint")
        confidence += 0.05

    blast_radius = sorted({peer for peer in peer_containers if peer != container_name})
    if blast_radius:
        evidence.append(f"peer_impact:{len(blast_radius)}")
        confidence += 0.15

    return CorrelationResult(
        incident_group=grouped or _new_group(container_name, fingerprint),
        confidence=round(min(0.99, confidence), 2),
        evidence=evidence,
        blast_radius=blast_radius,
    )
