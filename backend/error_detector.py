import re

_PATTERN = re.compile(
    r"error|fatal|critical|exception|traceback|panic:|sigkill|"
    r"oom|out of memory|connection refused|connection reset|"
    r"timeout|timed out|\bfailed\b|refused|unavailable|"
    r"stack trace|core dump|segfault|killed|abort",
    re.IGNORECASE,
)

_LEVEL_ERROR = re.compile(r"\b(ERROR|FATAL|CRITICAL)\b")
_LEVEL_WARN = re.compile(r"\b(WARN|WARNING)\b")


def is_suspicious(line: str) -> bool:
    return bool(_PATTERN.search(line))


def detect_level(line: str) -> str:
    if _LEVEL_ERROR.search(line):
        return "error"
    if _LEVEL_WARN.search(line):
        return "warning"
    if is_suspicious(line):
        return "warning"
    return "info"


def filter_suspicious(lines: list[str]) -> list[str]:
    return [l for l in lines if is_suspicious(l)]
