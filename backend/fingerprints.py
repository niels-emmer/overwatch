from __future__ import annotations

import hashlib
import re
from datetime import datetime

_UUID_RE = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b")
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_HEX_RE = re.compile(r"\b0x[0-9a-fA-F]+\b")
_NUMBER_RE = re.compile(r"\d+")
_TS_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[^ ]*\s+")


def normalize_line(line: str) -> str:
    value = line.strip()
    value = _TS_PREFIX_RE.sub("", value)
    value = _UUID_RE.sub("<uuid>", value)
    value = _IP_RE.sub("<ip>", value)
    value = _HEX_RE.sub("<hex>", value)
    value = _NUMBER_RE.sub("<num>", value)
    return value.lower()


def fingerprint_log_text(log_text: str) -> str:
    normalized = "\n".join(normalize_line(line) for line in log_text.splitlines() if line.strip())
    if not normalized:
        normalized = "<empty>"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def merge_finding(existing, new_log_text: str, now: datetime, *, max_log_lines: int = 80) -> None:
    existing.occurrence_count = int(existing.occurrence_count or 1) + 1
    existing.last_seen_at = now

    history = [line for line in (existing.raw_logs or "").splitlines() if line.strip()]
    incoming = [line for line in new_log_text.splitlines() if line.strip()]
    merged = (history + incoming)[-max_log_lines:]
    existing.raw_logs = "\n".join(merged)
