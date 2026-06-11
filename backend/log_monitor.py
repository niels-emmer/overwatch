import asyncio
import logging
import queue as sync_queue
import threading
import time
import uuid
from collections import defaultdict
from collections import deque
from datetime import datetime
from typing import Callable, Awaitable

import docker
from docker.errors import DockerException

from anomaly import AnomalyScorer
from config import Config
from error_detector import is_suspicious, detect_level

logger = logging.getLogger(__name__)


class ContainerLogStream:
    def __init__(self, container_id: str, container_name: str, loop: asyncio.AbstractEventLoop):
        self.container_id = container_id
        self.container_name = container_name
        self._loop = loop
        self._queue: sync_queue.Queue[str | None] = sync_queue.Queue(maxsize=2000)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, daemon=True, name=f"log-{self.container_name[:20]}"
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._queue.put(None)  # unblock any consumer

    def _run(self) -> None:
        try:
            client = docker.from_env()
            container = client.containers.get(self.container_id)
            since = int(time.time()) - 10
            for chunk in container.logs(stream=True, follow=True, since=since, timestamps=True):
                if self._stop.is_set():
                    break
                line = chunk.decode("utf-8", errors="replace").strip()
                if line:
                    try:
                        self._queue.put_nowait(line)
                    except sync_queue.Full:
                        pass
        except DockerException as e:
            logger.warning(f"Log stream ended for {self.container_name}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in log stream {self.container_name}: {e}")

    async def lines(self):
        """Async generator yielding log lines from this container."""
        while not self._stop.is_set():
            try:
                line = self._queue.get_nowait()
                if line is None:
                    return
                yield line
            except sync_queue.Empty:
                await asyncio.sleep(0.05)


class LogMonitor:
    def __init__(self, config: Config, broadcast: Callable[[dict], Awaitable[None]]):
        self._config = config
        self._broadcast = broadcast
        self._streams: dict[str, ContainerLogStream] = {}
        self._windows: dict[str, list[tuple[float, str]]] = defaultdict(list)
        self._recent_logs: dict[str, deque[str]] = defaultdict(lambda: deque(maxlen=120))
        self._containers: list[dict] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._running = False
        self._on_finding: Callable[[str, str, str, dict], Awaitable[None]] | None = None
        self._anomaly = AnomalyScorer(
            anomaly_threshold=self._config.monitor.anomaly_score_threshold,
            risk_threshold=self._config.monitor.risk_score_threshold,
        )

    def set_finding_callback(self, cb: Callable[[str, str, str, dict], Awaitable[None]]) -> None:
        """cb(container_name, log_text, finding_id, metadata)"""
        self._on_finding = cb

    def anomaly_snapshot(self, container_name: str | None = None) -> dict:
        return self._anomaly.snapshot(container_name)

    def risk_snapshot(self, container_name: str | None = None) -> dict:
        return self._anomaly.snapshot(container_name)

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._running = True
        asyncio.create_task(self._sync_containers())
        asyncio.create_task(self._flush_windows())

    async def stop(self) -> None:
        self._running = False
        for stream in self._streams.values():
            stream.stop()

    def _get_containers(self) -> list[dict]:
        try:
            client = docker.from_env()
            result = []
            for c in client.containers.list():
                image = c.image.tags[0] if c.image.tags else c.image.id[:12]
                result.append({
                    "id": c.id,
                    "name": c.name,
                    "status": c.status,
                    "image": image,
                })
            return result
        except Exception as e:
            logger.error(f"Cannot list containers: {e}")
            return []

    async def _sync_containers(self) -> None:
        while self._running:
            try:
                containers = await asyncio.to_thread(self._get_containers)
                running_ids = {c["id"] for c in containers}

                for c in containers:
                    if c["id"] not in self._streams:
                        stream = ContainerLogStream(c["id"], c["name"], self._loop)
                        self._streams[c["id"]] = stream
                        stream.start()
                        asyncio.create_task(self._drain_stream(c["id"], c["name"], stream))

                for cid in list(self._streams.keys()):
                    if cid not in running_ids:
                        self._streams[cid].stop()
                        del self._streams[cid]

                await self._broadcast({
                    "type": "container_status",
                    "data": {"containers": containers},
                })
                self._containers = containers
            except Exception as e:
                logger.error(f"Error in _sync_containers: {e}")
            await asyncio.sleep(10)

    async def _drain_stream(self, container_id: str, container_name: str, stream: ContainerLogStream) -> None:
        async for line in stream.lines():
            level = detect_level(line)
            ts = datetime.utcnow().isoformat()

            # Strip Docker timestamp prefix if present (format: 2024-01-01T00:00:00.000000000Z )
            text = line
            if len(line) > 35 and line[0].isdigit():
                parts = line.split(" ", 1)
                if len(parts) == 2:
                    text = parts[1]

            await self._broadcast({
                "type": "log_line",
                "data": {"container": container_name, "level": level, "text": text, "ts": ts},
            })
            self._recent_logs[container_name].append(text)

            if is_suspicious(text):
                self._windows[container_name].append((time.time(), text))

    def clear_cooldown(self, container_name: str) -> None:
        """Legacy no-op; duplicate suppression is handled at the DB layer in main.py."""
        return

    async def _flush_windows(self) -> None:
        window_secs = self._config.monitor.log_window_seconds
        threshold = self._config.monitor.min_error_lines_to_trigger
        while self._running:
            await asyncio.sleep(window_secs)
            cutoff = time.time() - window_secs

            for container_name in list(self._windows.keys()):
                recent = [(ts, l) for ts, l in self._windows[container_name] if ts >= cutoff]
                self._windows[container_name] = recent

                if not recent or not self._on_finding:
                    continue

                levels = [detect_level(l) for _, l in recent]
                max_level = "info"
                if "critical" in levels:
                    max_level = "critical"
                elif "error" in levels:
                    max_level = "error"
                elif "warning" in levels:
                    max_level = "warning"

                anomaly = self._anomaly.evaluate(
                    container_name=container_name,
                    threshold=threshold,
                    lines=[line for _, line in recent],
                    max_level=max_level,
                )

                if not anomaly.should_emit:
                    continue

                log_text = "\n".join(l for _, l in recent)
                finding_id = str(uuid.uuid4())
                self._windows[container_name] = []
                metadata = {
                    "anomaly_score": anomaly.score,
                    "risk_score": anomaly.risk_score,
                    "risk_horizon_minutes": anomaly.risk_horizon_minutes,
                    "baseline_rate": anomaly.baseline,
                    "drift_ratio": anomaly.drift_ratio,
                    "trigger_reasons": list(anomaly.reasons),
                    "suspicious_count": anomaly.suspicious_count,
                    "context": self._build_context(container_name, [line for _, line in recent]),
                }
                asyncio.create_task(self._on_finding(container_name, log_text, finding_id, metadata))

    def _build_context(self, container_name: str, recent_lines: list[str]) -> dict:
        container = next((c for c in self._containers if c.get("name") == container_name), {})

        stack_prefix = ""
        parts = container_name.split("-")
        if len(parts) >= 2:
            stack_prefix = "-".join(parts[:-1])

        peers = []
        if stack_prefix:
            peers = [
                c["name"]
                for c in self._containers
                if c.get("name", "").startswith(f"{stack_prefix}-") and c.get("name") != container_name
            ][:6]

        peer_logs = {
            peer: list(self._recent_logs.get(peer, []))[-5:]
            for peer in peers
        }

        return {
            "container": {
                "name": container_name,
                "status": container.get("status"),
                "image": container.get("image"),
            },
            "recent_error_lines": recent_lines[-12:],
            "peer_containers": peers,
            "peer_recent_logs": peer_logs,
        }
