# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Overwatch is an AI-powered Docker log monitor. It tails all running container logs, runs them through local Ollama models to detect errors and generate diagnostic plans, and surfaces findings in a live web UI where fixes can be approved and executed.

## Commands

### Backend (Python / FastAPI)

```bash
# Install dependencies
cd backend && pip install -r requirements.txt

# Run dev server (requires Docker socket access and Ollama running)
cd backend && uvicorn main:app --reload --port 8000

# No test suite yet — test manually with the integration approach in the plan
```

### Frontend (React / Vite / Tailwind)

```bash
cd frontend
npm install
npm run dev        # dev server on :5173, proxies /api and /ws to :8000
npm run build      # production build into dist/
```

### Docker (production)

```bash
# First-time setup
cp .env.example .env   # then edit OLLAMA_HOST if on Linux

# Build and run everything
docker compose up -d --build

# Dev mode with hot reload (backend + frontend separate ports)
docker compose -f docker-compose.dev.yml up

# Trigger a test finding manually
docker exec <container> sh -c 'for i in $(seq 1 5); do echo "ERROR: test failure $i" >&2; sleep 1; done'
```

UI is served on port `8090`. Both `OVERWATCH_PORT` and `OLLAMA_HOST` can be set in `.env` — Docker Compose loads it automatically.

## Architecture

### Data flow

```
Docker socket → log_monitor.py → error_detector.py (regex pre-filter)
                                         │ (≥3 suspicious lines in 30s window)
                                         ▼
                               ai_analyzer.py → Ollama qwen3:8b
                                         │ Finding (JSON)
                                         ▼
                               database.py (SQLite)
                                         ├── WebSocket broadcast → UI
                                         └── if severity ≥ threshold:
                                               ai_analyzer.py → Ollama devstral-small-2
                                                     │ DiagnosticPlan
                                                     └── WebSocket broadcast → UI
```

### Backend modules

- **`log_monitor.py`** — `LogMonitor` class manages per-container `ContainerLogStream` threads. Each stream runs in a `threading.Thread` reading Docker logs via the SDK, putting lines into a `queue.Queue`. `LogMonitor._drain_stream()` is an async task that reads from the queue and forwards to the WebSocket hub. `_flush_windows()` checks 30-second rolling buffers and fires findings when the threshold is met.
- **`error_detector.py`** — Cheap regex pre-filter. Runs on every log line before any Ollama call.
- **`ai_analyzer.py`** — Two async functions: `analyze_logs()` (uses `qwen3:8b`) and `generate_plan()` (uses `devstral-small-2`). Both prepend `/no_think\n` for qwen3-family models to skip extended thinking. Responses are parsed with `_extract_json()` which falls back to regex extraction if direct `json.loads` fails.
- **`action_executor.py`** — Thin wrapper around the Docker Python SDK. `restart_container()` and `exec_in_container()`. Called via `asyncio.to_thread()` from `main.py`.
- **`main.py`** — FastAPI app with a `WSHub` (set of WebSocket connections + broadcast). `on_finding()` is the callback from `LogMonitor` that runs analysis, persists to DB, broadcasts, and conditionally triggers plan generation. Actions are executed in `BackgroundTasks` and results broadcast via WebSocket.
- **`database.py`** — SQLAlchemy async with aiosqlite. Three tables: `findings`, `plans`, `audit_log`. DB path is `/app/data/overwatch.db` inside Docker, `../data/overwatch.db` locally.
- **`config.py`** — Loads `config/overwatch.yaml`. `OLLAMA_HOST` env var overrides yaml. `config.is_action_allowed()` validates action type + command against the allowlist before execution.

### Frontend

Single-page app with a three-panel layout (container sidebar / main tabbed area / plan panel). State lives in a Zustand store (`src/store/index.ts`). The WebSocket connection is established once in `useWebSocket.ts` and dispatches all server events into the store.

- **`ContainerGrid`** — Left sidebar. Click to filter logs/findings to one container.
- **`LogStream`** — Auto-scrolling log view. Respects `selectedContainer` filter.
- **`FindingsPanel`** — Cards for each finding; clicking one sets `activeFindingId`.
- **`PlanView`** — Right panel. Shows diagnostic steps and `ActionButton` components for each proposed action. Each action requires a confirm step before POSTing to `/api/plans/{id}/actions/{index}/execute`.
- **`AuditLog`** — Append-only log of all events fetched from `/api/audit` and appended via WebSocket `action_update` events.

### WebSocket event types (server → client)

| type | payload |
|------|---------|
| `container_status` | `{ containers: [...] }` |
| `log_line` | `{ container, level, text, ts }` |
| `finding` | full Finding object |
| `plan_ready` | full Plan object |
| `finding_updated` | `{ id, status }` |
| `action_update` | `{ plan_id, action_index, status, output?, label? }` |

### Config

`config/overwatch.yaml` controls Ollama models, the window/threshold parameters, and the action allowlist. The `allowed_actions` list is the security boundary — only `docker_restart` and explicitly listed `docker_exec` commands can be executed.

### Environment variables

| Variable | Default | Where set |
|----------|---------|-----------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | `.env` or shell; overrides `ollama.host` in yaml |
| `OVERWATCH_PORT` | `8090` | `.env` or shell |

Copy `.env.example` → `.env` before first run. Docker Compose loads it automatically.

### Key constraints

- The Docker socket is mounted **without** `:ro` so both log tailing and action execution (restart/exec) work. If you want to disable action execution, add `:ro` back and the `/api/plans/.../execute` endpoints will fail safely.
- Ollama is accessed at `host.docker.internal:11434` (Docker Desktop default). On Linux VPS, set `OLLAMA_HOST` in `.env` to the host's LAN IP, or add `extra_hosts: ["host.docker.internal:host-gateway"]` to the backend service in `docker-compose.yml`.
