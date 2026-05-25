import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, desc

import ai_analyzer
import action_executor
from config import load_config
from database import init_db, SessionLocal, Finding, Plan, AuditEntry
from fingerprints import fingerprint_log_text, merge_finding
from log_monitor import LogMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

config = load_config()

_SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}


class WSHub:
    def __init__(self):
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    async def broadcast(self, message: dict) -> None:
        if not self._connections:
            return
        data = json.dumps(message, default=str)
        dead: set[WebSocket] = set()
        for ws in list(self._connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._connections -= dead


hub = WSHub()
monitor: LogMonitor | None = None


async def on_finding(container_name: str, log_text: str, finding_id: str, metadata: dict | None = None) -> None:
    now = datetime.utcnow()
    fingerprint = fingerprint_log_text(log_text)
    metadata = metadata or {}
    trigger_reasons = metadata.get("trigger_reasons", [])

    # Merge repeated incidents by fingerprint before running any model analysis.
    async with SessionLocal() as session:
        existing_q = select(Finding).where(
            Finding.container_name == container_name,
            Finding.status == "open",
            Finding.fingerprint == fingerprint,
        ).order_by(desc(Finding.last_seen_at)).limit(1)
        existing = (await session.execute(existing_q)).scalar_one_or_none()
        if existing:
            merge_finding(existing, log_text, now)
            session.add(existing)
            await session.commit()
            await hub.broadcast(
                {
                    "type": "finding_updated",
                    "data": {
                        "id": existing.id,
                        "occurrence_count": existing.occurrence_count,
                        "last_seen_at": existing.last_seen_at.isoformat() if existing.last_seen_at else None,
                        "raw_logs": existing.raw_logs,
                    },
                }
            )
            return

    # DB-level cooldown guard for truly new incidents in the same container.
    # Novel fingerprint events bypass this gate to avoid dropping new issues.
    cooldown_cutoff = datetime.utcnow() - timedelta(minutes=config.monitor.cooldown_minutes)
    async with SessionLocal() as session:
        q = select(Finding).where(
            Finding.container_name == container_name,
            Finding.status == "open",
            Finding.detected_at >= cooldown_cutoff,
        ).limit(1)
        if (await session.execute(q)).scalar_one_or_none() and "novel_fingerprint" not in trigger_reasons:
            logger.debug(f"Suppressing duplicate finding for {container_name} — open finding within cooldown window")
            return

    result = await ai_analyzer.analyze_logs(container_name, log_text, config)
    if not result:
        return

    threshold = _SEVERITY_ORDER.get(config.monitor.finding_severity_threshold, 1)
    sev_val = _SEVERITY_ORDER.get(result["severity"], 2)

    finding = Finding(
        id=finding_id,
        container_name=container_name,
        detected_at=now,
        severity=result["severity"],
        summary=result["summary"],
        root_cause=result.get("root_cause"),
        raw_logs=log_text,
        status="open",
        fingerprint=fingerprint,
        first_seen_at=now,
        last_seen_at=now,
        occurrence_count=1,
        anomaly_score=metadata.get("anomaly_score"),
        trigger_reasons=json.dumps(trigger_reasons),
    )

    async with SessionLocal() as session:
        session.add(finding)
        audit = AuditEntry(
            event_type="finding_detected",
            container_name=container_name,
            details=f"{result['summary']} (reasons: {', '.join(trigger_reasons) if trigger_reasons else 'threshold'})",
        )
        session.add(audit)
        await session.commit()

    await hub.broadcast({"type": "finding", "data": finding.to_dict()})

    if sev_val >= threshold:
        asyncio.create_task(generate_plan_for(finding_id, container_name, result))


async def generate_plan_for(finding_id: str, container_name: str, finding_data: dict) -> None:
    plan_data = await ai_analyzer.generate_plan(finding_data, container_name, config)
    if not plan_data:
        return

    plan = Plan(
        id=str(uuid.uuid4()),
        finding_id=finding_id,
        created_at=datetime.utcnow(),
        steps=json.dumps(plan_data["steps"]),
        proposed_actions=json.dumps(plan_data["proposed_actions"]),
        status="pending",
    )

    async with SessionLocal() as session:
        session.add(plan)
        await session.commit()

    await hub.broadcast({"type": "plan_ready", "data": plan.to_dict()})


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor
    await init_db()
    monitor = LogMonitor(config, hub.broadcast)
    monitor.set_finding_callback(on_finding)
    await monitor.start()
    logger.info("Overwatch started")
    yield
    if monitor:
        await monitor.stop()
    logger.info("Overwatch stopped")


app = FastAPI(title="Overwatch", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)


@app.get("/api/findings")
async def get_findings(limit: int = 50, status: str | None = None):
    async with SessionLocal() as session:
        q = select(Finding).order_by(desc(Finding.detected_at)).limit(limit)
        if status:
            q = q.where(Finding.status == status)
        result = await session.execute(q)
        findings = result.scalars().all()

        # Attach plans
        out = []
        for f in findings:
            d = f.to_dict()
            pq = select(Plan).where(Plan.finding_id == f.id).order_by(desc(Plan.created_at)).limit(1)
            pr = await session.execute(pq)
            plan = pr.scalar_one_or_none()
            d["plan"] = plan.to_dict() if plan else None
            out.append(d)
        return out


@app.get("/api/findings/{finding_id}")
async def get_finding(finding_id: str):
    async with SessionLocal() as session:
        f = await session.get(Finding, finding_id)
        if not f:
            raise HTTPException(404, "Not found")
        d = f.to_dict()
        pq = select(Plan).where(Plan.finding_id == finding_id).order_by(desc(Plan.created_at)).limit(1)
        pr = await session.execute(pq)
        plan = pr.scalar_one_or_none()
        d["plan"] = plan.to_dict() if plan else None
        return d


@app.post("/api/findings/{finding_id}/dismiss")
async def dismiss_finding(finding_id: str):
    async with SessionLocal() as session:
        f = await session.get(Finding, finding_id)
        if not f:
            raise HTTPException(404, "Not found")
        container_name = f.container_name
        f.status = "dismissed"
        audit = AuditEntry(event_type="finding_dismissed", container_name=container_name)
        session.add(audit)
        await session.commit()
    # Clear cooldown so the container can raise new findings immediately after dismissal
    if monitor:
        monitor.clear_cooldown(container_name)
    await hub.broadcast({"type": "finding_updated", "data": {"id": finding_id, "status": "dismissed"}})
    return {"ok": True}


@app.post("/api/plans/{plan_id}/actions/{action_index}/execute")
async def execute_action(plan_id: str, action_index: int, background_tasks: BackgroundTasks):
    async with SessionLocal() as session:
        plan = await session.get(Plan, plan_id)
        if not plan:
            raise HTTPException(404, "Plan not found")
        actions = json.loads(plan.proposed_actions)
        if action_index >= len(actions):
            raise HTTPException(400, "Invalid action index")
        action = actions[action_index]

    action_type = action.get("action_type")
    container_name = action.get("container_name", "")
    command = action.get("command")

    if not config.is_action_allowed(action_type, command):
        raise HTTPException(403, f"Action not permitted: {action_type} {command}")

    await hub.broadcast({
        "type": "action_update",
        "data": {"plan_id": plan_id, "action_index": action_index, "status": "executing", "label": action.get("label")},
    })

    background_tasks.add_task(_run_action, plan_id, action_index, action_type, container_name, command, action)
    return {"status": "executing"}


async def _run_action(plan_id: str, action_index: int, action_type: str, container_name: str, command: str | None, action: dict) -> None:
    if action_type == "docker_restart":
        result = await asyncio.to_thread(action_executor.restart_container, container_name)
    elif action_type == "docker_exec":
        result = await asyncio.to_thread(action_executor.exec_in_container, container_name, command or "")
    else:
        result = {"success": False, "output": f"Unknown action type: {action_type}"}

    status = "done" if result["success"] else "failed"

    async with SessionLocal() as session:
        audit = AuditEntry(
            event_type="action_executed",
            container_name=container_name,
            action=f"{action_type}: {command or container_name}",
            result=status,
            details=result.get("output", ""),
        )
        session.add(audit)
        await session.commit()

    await hub.broadcast({
        "type": "action_update",
        "data": {
            "plan_id": plan_id,
            "action_index": action_index,
            "status": status,
            "output": result.get("output", ""),
            "label": action.get("label"),
        },
    })


@app.get("/api/audit")
async def get_audit(limit: int = 100):
    async with SessionLocal() as session:
        q = select(AuditEntry).order_by(desc(AuditEntry.timestamp)).limit(limit)
        result = await session.execute(q)
        return [e.to_dict() for e in result.scalars().all()]


@app.get("/api/config")
async def get_config():
    return {
        "analysis_model": config.ollama.analysis_model,
        "planning_model": config.ollama.planning_model,
        "ollama_host": config.ollama.host,
        "allowed_actions": [
            {"type": a.type, "commands": a.commands} for a in config.allowed_actions
        ],
    }


@app.get("/api/anomaly")
async def get_anomaly(container_name: str | None = None):
    if not monitor:
        return {}
    return monitor.anomaly_snapshot(container_name)
