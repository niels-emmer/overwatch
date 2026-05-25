import json
import logging
import os
import re

import httpx

from config import Config

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}


def _stub_enabled() -> bool:
    return os.getenv("OVERWATCH_AI_STUB", "0") == "1"


def _stub_response(system: str, user: str) -> str:
    if "proposed_actions" in system:
        return json.dumps(
            {
                "steps": [
                    {
                        "step": "Inspect recent errors",
                        "description": "Review the most recent suspicious lines for repeated failures.",
                    }
                ],
                "proposed_actions": [
                    {
                        "label": "Restart container",
                        "action_type": "docker_restart",
                        "command": None,
                        "container_name": "",
                    }
                ],
            }
        )

    severity = "ERROR" if "error" in user.lower() else "WARNING"
    return json.dumps(
        {
            "severity": severity,
            "summary": "Stub analysis detected a suspicious pattern.",
            "root_cause": "Stub mode enabled for deterministic testing.",
            "confidence": 0.9,
        }
    )


def _no_think_prefix(model: str) -> str:
    return "/no_think\n" if "qwen3" in model.lower() else ""


def _extract_json(text: str) -> dict:
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Extract first JSON object from text
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {}


async def analyze_logs(container_name: str, log_text: str, config: Config) -> dict | None:
    model = config.ollama.analysis_model
    prefix = _no_think_prefix(model)

    system = (
        "You are a senior DevOps engineer. Analyze the Docker container log excerpt and return "
        "a JSON object with exactly these keys: "
        "severity (one of INFO/WARNING/ERROR/CRITICAL), "
        "summary (one clear sentence), "
        "root_cause (brief hypothesis), "
        "confidence (0.0 to 1.0). "
        "Return ONLY valid JSON, no markdown, no explanation."
    )
    user = f"{prefix}Container: {container_name}\n\nLogs:\n{log_text}"

    result = await _chat(model, system, user, config.ollama.host)
    if not result:
        return None

    data = _extract_json(result)
    severity = data.get("severity", "ERROR").upper()
    if severity not in _SEVERITY_ORDER:
        severity = "ERROR"

    return {
        "severity": severity,
        "summary": data.get("summary", "Unknown error detected"),
        "root_cause": data.get("root_cause", ""),
        "confidence": float(data.get("confidence", 0.5)),
    }


async def generate_plan(finding: dict, container_name: str, config: Config) -> dict | None:
    model = config.ollama.planning_model
    prefix = _no_think_prefix(model)

    system = (
        "You are a senior DevOps engineer. Given a finding about a Docker container, return a JSON object with: "
        "steps (array of {step: string, description: string}) and "
        "proposed_actions (array of {label: string, action_type: 'docker_restart'|'docker_exec', "
        "command: string|null, container_name: string}). "
        "Only propose safe actions: docker restart or specific exec commands. "
        "IMPORTANT: exec commands run inside the target container which may be a minimal image. "
        "Never use curl or docker — they are rarely present inside containers. "
        "Prefer: wget -q -O- <url>, nc -zw3 <host> <port>, "
        "or python3 -c \"import urllib.request; urllib.request.urlopen('<url>')\" "
        "for connectivity checks. Use only POSIX shell builtins and tools present in busybox/alpine by default. "
        "Return ONLY valid JSON."
    )
    user = (
        f"{prefix}Container: {container_name}\n"
        f"Severity: {finding['severity']}\n"
        f"Summary: {finding['summary']}\n"
        f"Root cause: {finding.get('root_cause', 'unknown')}\n\n"
        "Generate a diagnostic plan and proposed fix actions."
    )

    result = await _chat(model, system, user, config.ollama.host)
    if not result:
        return None

    data = _extract_json(result)
    steps = data.get("steps", [])
    actions = data.get("proposed_actions", [])

    # Ensure container_name is set on all actions
    for a in actions:
        if not a.get("container_name"):
            a["container_name"] = container_name

    return {"steps": steps, "proposed_actions": actions}


async def _chat(model: str, system: str, user: str, host: str) -> str | None:
    if _stub_enabled():
        return _stub_response(system, user)

    url = f"{host.rstrip('/')}/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": "json",
    }
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")
    except Exception as e:
        logger.error(f"Ollama request failed ({model}): {e}")
        return None
