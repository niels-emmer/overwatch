# Overwatch

AI-powered Docker log monitor with a live web UI. Overwatch tails all running container logs, detects errors automatically, and uses local [Ollama](https://ollama.ai) models to diagnose problems and propose fixes — no cloud APIs, no cost per query.

> Designed to run alongside [Dozzle](https://github.com/amir20/dozzle) on a home server or VPS. Dozzle gives you raw log access; Overwatch gives you the AI layer on top.

---

## Features

- **Live log streaming** — all Docker containers, color-coded by severity, filterable per container
- **Automatic error detection** — regex pre-filter catches errors/exceptions/OOM/timeouts before touching the LLM
- **AI analysis** — suspicious log windows are sent to a local Ollama model for structured diagnosis (severity, summary, root cause)
- **Diagnostic plans** — a second model generates step-by-step investigation steps and proposed fix actions
- **One-click fixes** — restart a container or run an allowlisted `exec` command directly from the UI, with a confirm dialog
- **Audit log** — every finding, plan, and executed action is persisted to SQLite
- **Fully local** — uses `qwen3:8b` for analysis and `devstral-small-2` for planning by default; both configurable

---

## Screenshot

```
┌─────────────────────────────────────────────────────────────┐
│ OVERWATCH                                    ● 2 open findings│
├────────────┬────────────────────────────┬───────────────────┤
│ nginx   ✓  │  [Logs] [Findings] [Audit] │  FINDING: nginx   │
│ postgres✓  │                            │  ERROR: OOM kill  │
│ redis   ✗2 │  13:42:01 redis  ERR ...  │  ───────────────  │
│ app     ✓  │  13:42:02 redis  ERR ...  │  DIAGNOSTIC PLAN  │
│            │  13:42:03 nginx  INF ...  │  1. Check memory  │
│            │  13:42:04 app    INF ...  │  2. Check limits  │
│            │                            │  ───────────────  │
│            │                            │  [↻ Restart redis]│
│            │                            │  [✓ Dismiss]      │
└────────────┴────────────────────────────┴───────────────────┘
```

---

## Requirements

- Docker + Docker Compose (on the target host)
- [Ollama](https://ollama.ai) reachable on the LAN (same host or any other machine), with at least one capable model pulled
- LAN access to the VPS/server from your browser

Recommended models (pull these before starting):

```bash
ollama pull qwen3:8b          # analysis — fast, strong reasoning
ollama pull devstral-small-2  # planning — code/DevOps-focused
```

Any instruction-following model works. Edit `config/overwatch.yaml` to use what you have.

---

## Installation

### Production (recommended)

```bash
git clone https://github.com/your-username/overwatch.git
cd overwatch

# Set up environment
cp .env.example .env
nano .env                      # adjust OLLAMA_HOST if on Linux (see note below)

# Optional: adjust models, thresholds, allowed actions
nano config/overwatch.yaml

docker compose up -d --build
```

The UI is available at `http://<host-ip>:8090`.

**Linux VPS note:** `host.docker.internal` does not resolve on Linux by default. Set `OLLAMA_HOST` in `.env` to your host's LAN IP:

```dotenv
OLLAMA_HOST=http://192.168.1.x:11434
```

Or add this to the backend service in `docker-compose.yml` instead:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

### Development

```bash
# Terminal 1 — backend with hot reload (port 8000)
docker compose -f docker-compose.dev.yml up backend

# Terminal 2 — frontend dev server with HMR (port 5173)
cd frontend && npm install && npm run dev
```

The Vite dev server proxies `/api` and `/ws` to the backend automatically.

---

## Configuration

### Environment variables

Copy [`.env.example`](.env.example) to `.env` — Docker Compose loads it automatically.

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_HOST` | `http://host.docker.internal:11434` | Ollama API URL. Can point to any host on the LAN, not just the VPS itself. |
| `OVERWATCH_PORT` | `8090` | Port the web UI is exposed on. |

### `config/overwatch.yaml`

```yaml
ollama:
  host: http://host.docker.internal:11434  # overridden by OLLAMA_HOST env var
  analysis_model: qwen3:8b        # used for: severity / summary / root cause
  planning_model: devstral-small-2 # used for: diagnostic steps + proposed actions

monitor:
  log_window_seconds: 30          # rolling window size for grouping errors
  min_error_lines_to_trigger: 3   # how many suspicious lines trigger an analysis
  finding_severity_threshold: WARNING  # minimum severity to generate a plan

allowed_actions:
  - type: docker_restart
    description: Restart a container
  - type: docker_exec
    commands:
      - "nginx -s reload"
      - "supervisorctl restart all"
      - "kill -HUP 1"
```

Only commands listed under `docker_exec.commands` can be executed from the UI. Add entries here to unlock additional fix actions.

---

## How it works

```
Docker socket
    │
    ▼
Log monitor — tails all running containers via Docker SDK (one thread per container)
    │
    ▼
Error detector — cheap regex pre-filter (ERROR, FATAL, Exception, OOM, timeout, ...)
    │  (≥ N suspicious lines in a 30s window)
    ▼
AI analyzer ──► Ollama qwen3:8b
    │              returns: severity, summary, root cause, confidence
    ▼
SQLite (findings table) + WebSocket broadcast → UI
    │
    └── if severity ≥ threshold:
          AI analyzer ──► Ollama devstral-small-2
                           returns: diagnostic steps + proposed actions
                        SQLite (plans table) + WebSocket broadcast → UI

User clicks "Execute" in UI → confirm dialog → POST /api/plans/.../execute
    │
    ▼
Action executor (docker restart / exec, via Docker SDK)
    │
    ▼
SQLite (audit_log table) + WebSocket broadcast → UI
```

The regex pre-filter means Ollama is only invoked when something actually looks wrong — healthy containers produce zero LLM calls.

---

## Upgrading

```bash
git pull
docker compose up -d --build
```

The SQLite database in `data/` persists across upgrades automatically. If a schema change is needed in a future version, it will be noted in the release notes.

---

## Debugging

**UI shows "connecting..." and never connects**

Check that the backend started successfully:
```bash
docker compose logs backend
```
On Linux, verify Ollama is reachable from inside the container:
```bash
docker exec overwatch-backend-1 curl http://host.docker.internal:11434/api/tags
```
If it fails, set `OLLAMA_HOST` to your host's LAN IP or add `extra_hosts: ["host.docker.internal:host-gateway"]` to the backend service in `docker-compose.yml`.

**No containers appear in the sidebar**

The backend needs access to the Docker socket. Verify the volume mount:
```bash
docker inspect overwatch-backend-1 | grep -A5 Mounts
```
The socket `/var/run/docker.sock` must be present. On some systems you may need to add the container user to the `docker` group.

**No findings are generated despite visible errors**

The pre-filter requires at least 3 suspicious lines within the configured window (default: 30 seconds). You can trigger a synthetic finding to test the full pipeline:
```bash
docker exec <any-container> sh -c \
  'for i in $(seq 1 5); do echo "ERROR: synthetic test failure $i" >&2; sleep 2; done'
```
Wait up to 30 seconds for the analysis to appear.

**Ollama requests are slow or time out**

Switch to a smaller model in `config/overwatch.yaml`:
```yaml
ollama:
  analysis_model: qwen3:1.7b
  planning_model: qwen3:8b
```
`qwen3:1.7b` (1.4 GB) is very fast and sufficient for log analysis.

**Actions are rejected with 403**

The command must be explicitly listed in `allowed_actions.commands` in `config/overwatch.yaml`. Add it and restart the backend container:
```bash
docker compose restart backend
```

**Database is missing or corrupted**

The database lives at `data/overwatch.db`. To reset:
```bash
docker compose down
rm data/overwatch.db
docker compose up -d
```

---

## Project structure

```
overwatch/
├── backend/
│   ├── main.py              # FastAPI app, WebSocket hub, API routes
│   ├── log_monitor.py       # Docker log tailing + window accumulation
│   ├── error_detector.py    # Regex pre-filter
│   ├── ai_analyzer.py       # Ollama HTTP client (analysis + planning)
│   ├── action_executor.py   # docker restart / exec
│   ├── database.py          # SQLAlchemy async + SQLite models
│   └── config.py            # YAML config loader
├── frontend/
│   └── src/
│       ├── App.tsx           # Three-panel layout + tab bar
│       ├── store/index.ts    # Zustand global state
│       ├── hooks/useWebSocket.ts
│       └── components/
│           ├── ContainerGrid.tsx   # Sidebar with health dots
│           ├── LogStream.tsx       # Live log view
│           ├── FindingsPanel.tsx   # AI finding cards
│           ├── PlanView.tsx        # Diagnostic plan + action buttons
│           └── AuditLog.tsx        # History table
├── config/
│   └── overwatch.yaml       # Models, thresholds, allowed actions
├── data/                    # SQLite database (gitignored)
├── .env.example             # Environment variable template
├── docker-compose.yml       # Production
└── docker-compose.dev.yml   # Development with hot reload
```

---

## Credits

**Built with:**

- [FastAPI](https://fastapi.tiangolo.com) — Python async web framework
- [Ollama](https://ollama.ai) — local LLM inference runtime
- [qwen3:8b](https://ollama.ai/library/qwen3) by Alibaba — log analysis model
- [devstral-small-2](https://ollama.ai/library/devstral) by Mistral AI — diagnostic planning model
- [Docker Python SDK](https://docker-py.readthedocs.io) — container log streaming and action execution
- [SQLAlchemy](https://www.sqlalchemy.org) + [aiosqlite](https://github.com/omnilib/aiosqlite) — async SQLite persistence
- [React](https://react.dev) + [Vite](https://vitejs.dev) — frontend framework and build tool
- [Tailwind CSS](https://tailwindcss.com) — styling
- [Zustand](https://zustand-demo.pmnd.rs) — frontend state management
- [Dozzle](https://github.com/amir20/dozzle) by Amir Raminfar — the log viewer this was designed to complement

**Designed and implemented by [Claude](https://claude.ai) (Anthropic claude-sonnet-4-6)**, based on a specification by Niels Emmer.
