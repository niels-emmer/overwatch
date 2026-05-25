from __future__ import annotations

import json
import re
from typing import Any


_SECRET_VALUE_RE = re.compile(r"(?i)(password|passwd|token|api[_-]?key|secret)\s*[:=]\s*([^\s,;]+)")


def redact_text(value: str) -> str:
    return _SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}=<redacted>", value)


def _sanitize(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, dict):
        return {k: _sanitize(v) for k, v in value.items()}
    return value


def _trim(value: Any, *, max_items: int = 12, max_text: int = 240) -> Any:
    if isinstance(value, str):
        return value if len(value) <= max_text else f"{value[:max_text]}..."
    if isinstance(value, list):
        return [_trim(v, max_items=max_items, max_text=max_text) for v in value[:max_items]]
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for idx, (k, v) in enumerate(value.items()):
            if idx >= max_items:
                break
            out[k] = _trim(v, max_items=max_items, max_text=max_text)
        return out
    return value


def build_context_block(context: dict[str, Any] | None, *, max_chars: int = 1600) -> str:
    if not context:
        return "{}"

    sanitized = _trim(_sanitize(context))
    block = json.dumps(sanitized, ensure_ascii=True, separators=(",", ":"))
    if len(block) > max_chars:
        return f"{block[:max_chars]}..."
    return block
