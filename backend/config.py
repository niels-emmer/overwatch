import os
from dataclasses import dataclass, field
from typing import Any
import yaml


@dataclass
class OllamaConfig:
    host: str = "http://host.docker.internal:11434"
    analysis_model: str = "qwen3:8b"
    planning_model: str = "devstral-small-2"


@dataclass
class MonitorConfig:
    log_window_seconds: int = 30
    min_error_lines_to_trigger: int = 3
    finding_severity_threshold: str = "WARNING"
    cooldown_minutes: int = 10


@dataclass
class AllowedAction:
    type: str
    description: str = ""
    commands: list[str] = field(default_factory=list)


@dataclass
class Config:
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    allowed_actions: list[AllowedAction] = field(default_factory=lambda: [
        AllowedAction(type="docker_restart", description="Restart a container"),
        AllowedAction(type="docker_exec", commands=["nginx -s reload", "supervisorctl restart all"]),
    ])

    def is_action_allowed(self, action_type: str, command: str | None = None) -> bool:
        for a in self.allowed_actions:
            if a.type == action_type:
                if action_type == "docker_restart":
                    return True
                if action_type == "docker_exec" and ("*" in a.commands or command in a.commands):
                    return True
        return False


def load_config(path: str = "/app/config/overwatch.yaml") -> Config:
    if not os.path.exists(path):
        path = os.path.join(os.path.dirname(__file__), "..", "config", "overwatch.yaml")
    if not os.path.exists(path):
        return Config()

    with open(path) as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}

    cfg = Config()

    if ollama := raw.get("ollama"):
        cfg.ollama = OllamaConfig(
            host=ollama.get("host", cfg.ollama.host),
            analysis_model=ollama.get("analysis_model", cfg.ollama.analysis_model),
            planning_model=ollama.get("planning_model", cfg.ollama.planning_model),
        )
    if mon := raw.get("monitor"):
        cfg.monitor = MonitorConfig(
            log_window_seconds=mon.get("log_window_seconds", cfg.monitor.log_window_seconds),
            min_error_lines_to_trigger=mon.get("min_error_lines_to_trigger", cfg.monitor.min_error_lines_to_trigger),
            finding_severity_threshold=mon.get("finding_severity_threshold", cfg.monitor.finding_severity_threshold),
            cooldown_minutes=mon.get("cooldown_minutes", cfg.monitor.cooldown_minutes),
        )
    if actions := raw.get("allowed_actions"):
        cfg.allowed_actions = [
            AllowedAction(
                type=a["type"],
                description=a.get("description", ""),
                commands=a.get("commands", []),
            )
            for a in actions
        ]

    ollama_env = os.environ.get("OLLAMA_HOST")
    if ollama_env:
        cfg.ollama.host = ollama_env

    return cfg
