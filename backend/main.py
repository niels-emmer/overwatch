import asyncio
import contextlib
import json
import logging
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

import ai_analyzer
import action_executor
from action_ranking import action_signature, classify_outcome, rank_actions, OutcomeSnapshot
from action_policy import evaluate_policy
from config import load_config
from correlation import correlate_incident, stack_prefix
from database import init_db, SessionLocal, Finding, Plan, AuditEntry, IncidentOutcome, ServiceBaseline
from fingerprints import fingerprint_log_text, merge_finding
from lifecycle import is_valid_transition, status_after_successful_action, status_for_regression
from log_monitor import LogMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

config = load_config()

_SEVERITY_ORDER = {"INFO": 0, "WARNING": 1, "ERROR": 2, "CRITICAL": 3}
_AUTO_HISTORY: dict[str, deque[datetime]] = defaultdict(deque)


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
server_started_at: datetime | None = None
_baseline_sync_task: asyncio.Task | None = None


class FindingStatusUpdate(BaseModel):
    status: str


class PolicyTemplateUpdate(BaseModel):
    template: str


async def on_finding(container_name: str, log_text: str, finding_id: str, metadata: dict | None = None) -> None:
    now = datetime.utcnow()
    fingerprint = fingerprint_log_text(log_text)
    metadata = metadata or {}
    trigger_reasons = metadata.get("trigger_reasons", [])

    # Merge repeated incidents by fingerprint before running any model analysis.
    async with SessionLocal() as session:
        existing_q = select(Finding).where(
            Finding.container_name == container_name,
            Finding.fingerprint == fingerprint,
            Finding.status != "dismissed",
        ).order_by(desc(Finding.last_seen_at)).limit(1)
        existing = (await session.execute(existing_q)).scalar_one_or_none()
        if existing:
            merge_finding(existing, log_text, now)
            if metadata.get("anomaly_score") is not None:
                existing.anomaly_score = metadata.get("anomaly_score")
            if metadata.get("risk_score") is not None:
                existing.risk_score = metadata.get("risk_score")
            if metadata.get("risk_horizon_minutes") is not None:
                existing.risk_horizon_minutes = metadata.get("risk_horizon_minutes")
            if trigger_reasons:
                existing.trigger_reasons = json.dumps(trigger_reasons)
            regressed = status_for_regression(existing.status)
            if regressed:
                existing.status = regressed
            session.add(existing)
            await session.commit()
            await hub.broadcast(
                {
                    "type": "finding_updated",
                    "data": {
                        "id": existing.id,
                        "status": existing.status,
                        "occurrence_count": existing.occurrence_count,
                        "last_seen_at": existing.last_seen_at.isoformat() if existing.last_seen_at else None,
                        "raw_logs": existing.raw_logs,
                        "anomaly_score": existing.anomaly_score,
                        "risk_score": existing.risk_score,
                        "risk_horizon_minutes": existing.risk_horizon_minutes,
                        "trigger_reasons": json.loads(existing.trigger_reasons) if existing.trigger_reasons else [],
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
            Finding.status.in_(["open", "investigating", "regressed"]),
            Finding.detected_at >= cooldown_cutoff,
        ).limit(1)
        if (await session.execute(q)).scalar_one_or_none() and "novel_fingerprint" not in trigger_reasons:
            logger.debug(f"Suppressing duplicate finding for {container_name} — open finding within cooldown window")
            return

    result = await ai_analyzer.analyze_logs(
        container_name,
        log_text,
        config,
        context=metadata.get("context"),
    )
    if not result:
        return

    threshold = _SEVERITY_ORDER.get(config.monitor.finding_severity_threshold, 1)
    sev_val = _SEVERITY_ORDER.get(result["severity"], 2)

    peer_context = (metadata.get("context") or {}).get("peer_containers") or []
    async with SessionLocal() as session:
        prefix = stack_prefix(container_name)
        candidate_q = select(Finding).where(
            Finding.status.in_(["open", "investigating", "regressed", "mitigated"]),
            Finding.container_name.like(f"{prefix}-%"),
        ).order_by(desc(Finding.last_seen_at)).limit(10)
        candidates = (await session.execute(candidate_q)).scalars().all()
    corr = correlate_incident(
        container_name=container_name,
        fingerprint=fingerprint,
        trigger_reasons=trigger_reasons,
        peer_containers=peer_context,
        candidate_groups=[(c.incident_group or "", c.container_name, c.last_seen_at) for c in candidates if c.incident_group],
    )

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
        risk_score=metadata.get("risk_score"),
        risk_horizon_minutes=metadata.get("risk_horizon_minutes"),
        trigger_reasons=json.dumps(trigger_reasons),
        incident_group=corr.incident_group,
        correlation_confidence=corr.confidence,
        correlation_evidence=json.dumps(corr.evidence),
        blast_radius=json.dumps(corr.blast_radius),
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
        asyncio.create_task(generate_plan_for(finding_id, container_name, result, metadata.get("context")))


async def generate_plan_for(finding_id: str, container_name: str, finding_data: dict, context: dict | None = None) -> None:
    plan_data = await ai_analyzer.generate_plan(finding_data, container_name, config, context=context)
    if not plan_data:
        return

    async with SessionLocal() as session:
        finding = await session.get(Finding, finding_id)
        snapshots = await _load_outcome_snapshots(
            session,
            finding.fingerprint if finding else None,
            container_name,
        )
    ranked_actions = rank_actions(plan_data.get("proposed_actions", []), snapshots)

    plan = Plan(
        id=str(uuid.uuid4()),
        finding_id=finding_id,
        created_at=datetime.utcnow(),
        steps=json.dumps(plan_data["steps"]),
        proposed_actions=json.dumps(ranked_actions),
        status="pending",
    )

    async with SessionLocal() as session:
        session.add(plan)
        await session.commit()

    await hub.broadcast({"type": "plan_ready", "data": plan.to_dict()})
    await _maybe_auto_remediate(plan, ranked_actions, finding)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor, server_started_at, _baseline_sync_task
    await init_db()
    server_started_at = datetime.utcnow()
    monitor = LogMonitor(config, hub.broadcast)
    monitor.set_finding_callback(on_finding)
    await monitor.start()
    _baseline_sync_task = asyncio.create_task(_sync_risk_baselines())
    logger.info("Overwatch started")
    yield
    if _baseline_sync_task:
        _baseline_sync_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _baseline_sync_task
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


@app.post("/api/findings/{finding_id}/status")
async def update_finding_status(finding_id: str, payload: FindingStatusUpdate):
    async with SessionLocal() as session:
        finding = await session.get(Finding, finding_id)
        if not finding:
            raise HTTPException(404, "Not found")

        target = payload.status.strip().lower()
        if not is_valid_transition(finding.status, target):
            raise HTTPException(400, f"Invalid status transition: {finding.status} -> {target}")

        finding.status = target
        session.add(
            AuditEntry(
                event_type="finding_status_changed",
                container_name=finding.container_name,
                details=f"{finding_id}: {target}",
            )
        )
        await session.commit()

    await hub.broadcast({"type": "finding_updated", "data": {"id": finding_id, "status": target}})
    return {"ok": True, "status": target}


@app.post("/api/plans/{plan_id}/actions/{action_index}/execute")
async def execute_action(
    plan_id: str,
    action_index: int,
    background_tasks: BackgroundTasks,
    x_overwatch_high_approval: str | None = Header(default=None),
):
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

    policy = evaluate_policy(
        action_type,
        command,
        high_risk_approved=(x_overwatch_high_approval or "").lower() == "approved",
    )
    if not policy.allowed:
        async with SessionLocal() as session:
            session.add(
                AuditEntry(
                    event_type="action_policy_blocked",
                    container_name=container_name,
                    action=f"{action_type}: {command or container_name}",
                    result=policy.risk,
                    details=policy.reason,
                )
            )
            await session.commit()
        raise HTTPException(403, policy.reason)

    await hub.broadcast({
        "type": "action_update",
        "data": {"plan_id": plan_id, "action_index": action_index, "status": "executing", "label": action.get("label")},
    })

    background_tasks.add_task(_run_action, plan_id, action_index, action_type, container_name, command, action)
    return {"status": "executing"}


async def _run_action(
    plan_id: str,
    action_index: int,
    action_type: str,
    container_name: str,
    command: str | None,
    action: dict,
    *,
    auto_triggered: bool = False,
) -> None:
    if action_type == "docker_restart":
        result = await asyncio.to_thread(action_executor.restart_container, container_name)
    elif action_type == "docker_exec":
        result = await asyncio.to_thread(action_executor.exec_in_container, container_name, command or "")
    else:
        result = {"success": False, "output": f"Unknown action type: {action_type}"}

    status = "done" if result["success"] else "failed"

    if auto_triggered and status == "done":
        verified = await _verify_auto_action(action_type, container_name)
        if not verified:
            status = "failed"
            result["output"] = f"{result.get('output', '').strip()}\nverification_failed: auto action did not reach healthy runtime state".strip()

    outcome_status = classify_outcome(status, result.get("output"))

    async with SessionLocal() as session:
        plan = await session.get(Plan, plan_id)
        finding = await session.get(Finding, plan.finding_id) if plan else None

        if finding and finding.fingerprint:
            await _record_incident_outcome(
                session,
                fingerprint=finding.fingerprint,
                container_name=finding.container_name,
                action_type=action_type,
                action_sig=action_signature(action_type, container_name, command),
                outcome_status=outcome_status,
            )

        audit_event = "auto_action_executed" if auto_triggered else "action_executed"
        audit = AuditEntry(
            event_type=audit_event,
            container_name=container_name,
            action=f"{action_type}: {command or container_name}",
            result=status,
            details=result.get("output", ""),
        )
        session.add(audit)
        await session.commit()

    if status == "done":
        async with SessionLocal() as session:
            plan = await session.get(Plan, plan_id)
            if plan:
                finding = await session.get(Finding, plan.finding_id)
                if finding:
                    if auto_triggered:
                        next_status = "resolved"
                    else:
                        next_status = status_after_successful_action(finding.status)
                    if next_status and finding.status != next_status:
                        finding.status = next_status
                        session.add(
                            AuditEntry(
                                event_type="finding_status_changed",
                                container_name=finding.container_name,
                                details=f"{finding.id}: {next_status}",
                            )
                        )
                        await session.commit()
                        await hub.broadcast({
                            "type": "finding_updated",
                            "data": {"id": finding.id, "status": next_status},
                        })
    elif auto_triggered:
        async with SessionLocal() as session:
            plan = await session.get(Plan, plan_id)
            if plan:
                finding = await session.get(Finding, plan.finding_id)
                if finding:
                    next_status = "regressed" if finding.status in {"mitigated", "resolved"} else finding.status
                    changed = next_status != finding.status
                    session.add(
                        AuditEntry(
                            event_type="auto_remediation_escalated",
                            container_name=finding.container_name,
                            details=f"{finding.id}: verification failed",
                        )
                    )
                    if changed:
                        finding.status = next_status
                    await session.commit()
                    if changed:
                        await hub.broadcast({
                            "type": "finding_updated",
                            "data": {"id": finding.id, "status": next_status},
                        })

    await hub.broadcast({
        "type": "action_update",
        "data": {
            "plan_id": plan_id,
            "action_index": action_index,
            "status": status,
            "output": result.get("output", ""),
            "label": f"[auto] {action.get('label')}" if auto_triggered else action.get("label"),
        },
    })


async def _verify_auto_action(action_type: str, container_name: str) -> bool:
    if action_type != "docker_restart":
        return True

    await asyncio.sleep(2)
    runtime = await asyncio.to_thread(action_executor.get_container_runtime, container_name)
    return bool(runtime.get("success") and runtime.get("running"))


def _auto_profile_enabled() -> bool:
    return config.monitor.auto_remediation_profile.lower() in {"conservative", "default", "aggressive"}


def _can_auto_remediate_now(container_name: str) -> bool:
    window = timedelta(minutes=config.monitor.auto_remediation_window_minutes)
    limit = max(1, config.monitor.auto_remediation_max_per_window)
    now = datetime.utcnow()
    history = _AUTO_HISTORY[container_name]

    while history and (now - history[0]) > window:
        history.popleft()
    return len(history) < limit


def _profile_allows_finding(finding: Finding | None) -> bool:
    if not finding:
        return False

    profile = config.monitor.auto_remediation_profile.lower()
    if profile == "aggressive":
        return True
    if profile == "default":
        return finding.severity in {"ERROR", "CRITICAL"}
    if profile == "conservative":
        return finding.severity == "CRITICAL"
    return False


async def _maybe_auto_remediate(plan: Plan, ranked_actions: list[dict], finding: Finding | None) -> None:
    if not ranked_actions or not _auto_profile_enabled():
        return
    if not _profile_allows_finding(finding):
        return

    action = ranked_actions[0]
    action_type = action.get("action_type")
    container_name = action.get("container_name", "")
    command = action.get("command")

    # Keep auto-remediation restricted to low-risk restart actions.
    policy = evaluate_policy(action_type, command, high_risk_approved=False)
    if action_type != "docker_restart" or policy.risk != "low" or not policy.allowed:
        async with SessionLocal() as session:
            session.add(
                AuditEntry(
                    event_type="auto_remediation_skipped",
                    container_name=container_name,
                    action=f"{action_type}: {command or container_name}",
                    result=policy.risk,
                    details="AUTO_POLICY_REQUIRES_LOW_RISK_RESTART",
                )
            )
            await session.commit()
        return

    if not _can_auto_remediate_now(container_name):
        async with SessionLocal() as session:
            session.add(
                AuditEntry(
                    event_type="auto_remediation_skipped",
                    container_name=container_name,
                    action=f"{action_type}: {container_name}",
                    result="rate_limited",
                    details="AUTO_RATE_LIMIT_EXCEEDED",
                )
            )
            await session.commit()
        return

    _AUTO_HISTORY[container_name].append(datetime.utcnow())

    await hub.broadcast({
        "type": "action_update",
        "data": {
            "plan_id": plan.id,
            "action_index": 0,
            "status": "executing",
            "label": f"[auto] {action.get('label')}",
        },
    })
    asyncio.create_task(
        _run_action(
            plan.id,
            0,
            action_type,
            container_name,
            command,
            action,
            auto_triggered=True,
        )
    )


async def _load_outcome_snapshots(
    session: AsyncSession,
    fingerprint: str | None,
    container_name: str,
) -> dict[str, OutcomeSnapshot]:
    if not fingerprint:
        return {}

    q = select(IncidentOutcome).where(
        IncidentOutcome.fingerprint == fingerprint,
        IncidentOutcome.container_name == container_name,
    )
    outcomes = (await session.execute(q)).scalars().all()
    return {
        row.action_signature: OutcomeSnapshot(
            success_count=row.success_count or 0,
            failure_count=row.failure_count or 0,
            timeout_count=row.timeout_count or 0,
            abort_count=row.abort_count or 0,
            last_seen_at=row.last_seen_at,
        )
        for row in outcomes
    }


async def _record_incident_outcome(
    session: AsyncSession,
    fingerprint: str,
    container_name: str,
    action_type: str,
    action_sig: str,
    outcome_status: str,
) -> None:
    q = select(IncidentOutcome).where(
        IncidentOutcome.fingerprint == fingerprint,
        IncidentOutcome.container_name == container_name,
        IncidentOutcome.action_signature == action_sig,
    ).limit(1)
    existing = (await session.execute(q)).scalar_one_or_none()

    if not existing:
        existing = IncidentOutcome(
            fingerprint=fingerprint,
            container_name=container_name,
            action_type=action_type,
            action_signature=action_sig,
            success_count=0,
            failure_count=0,
            timeout_count=0,
            abort_count=0,
        )

    if outcome_status == "success":
        existing.success_count = (existing.success_count or 0) + 1
    elif outcome_status == "timeout":
        existing.timeout_count = (existing.timeout_count or 0) + 1
    elif outcome_status == "abort":
        existing.abort_count = (existing.abort_count or 0) + 1
    else:
        existing.failure_count = (existing.failure_count or 0) + 1

    existing.last_status = outcome_status
    existing.last_seen_at = datetime.utcnow()
    session.add(existing)


def build_work_queue(findings: list[Finding], now: datetime | None = None) -> list[dict]:
    now = now or datetime.utcnow()
    queue: list[dict] = []
    for f in findings:
        blast = json.loads(f.blast_radius) if f.blast_radius else []
        age_minutes = max(0.0, (now - (f.detected_at or now)).total_seconds() / 60.0)
        risk = float(f.risk_score or 0.0)
        priority = risk + (len(blast) * 8.0) + min(20.0, age_minutes / 6.0)

        payload = f.to_dict()
        payload["priority_score"] = round(priority, 2)
        payload["blast_radius_size"] = len(blast)
        payload["age_minutes"] = round(age_minutes, 1)
        queue.append(payload)

    queue.sort(key=lambda item: item.get("priority_score", 0.0), reverse=True)
    return queue


def build_shift_summary(findings: list[Finding], audit: list[AuditEntry]) -> str:
    open_findings = [f for f in findings if f.status in {"open", "investigating", "regressed", "mitigated"}]
    resolved_findings = [f for f in findings if f.status in {"resolved", "dismissed"}]
    auto_actions = [a for a in audit if a.event_type == "auto_action_executed"]
    escalations = [a for a in audit if a.event_type == "auto_remediation_escalated"]

    lines = [
        "# Overwatch Shift Summary",
        "",
        f"- Open incidents: {len(open_findings)}",
        f"- Resolved/dismissed incidents: {len(resolved_findings)}",
        f"- Auto-actions executed: {len(auto_actions)}",
        f"- Auto-action escalations: {len(escalations)}",
        "",
        "## Highest Priority Incidents",
    ]

    for finding in open_findings[:5]:
        blast = json.loads(finding.blast_radius) if finding.blast_radius else []
        lines.append(
            f"- [{finding.severity}] {finding.container_name}: {finding.summary}"
            f" (risk={finding.risk_score or 0:.1f}, blast={len(blast)})"
        )

    if not open_findings:
        lines.append("- None")

    lines.extend(["", "## Pending Operator Actions"])
    pending_actions = [a for a in audit if a.event_type in {"action_policy_blocked", "auto_remediation_skipped"}]
    for entry in pending_actions[:5]:
        lines.append(f"- {entry.container_name or 'n/a'}: {entry.details or entry.action or entry.event_type}")
    if not pending_actions:
        lines.append("- None")

    return "\n".join(lines)


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
        "auto_remediation_profile": config.monitor.auto_remediation_profile,
    }


@app.get("/api/work-queue")
async def get_work_queue(limit: int = 50):
    async with SessionLocal() as session:
        q = select(Finding).where(
            Finding.status.in_(["open", "investigating", "regressed", "mitigated"])
        ).order_by(desc(Finding.detected_at)).limit(limit)
        findings = (await session.execute(q)).scalars().all()

    return {"items": build_work_queue(findings)}


@app.get("/api/summary/shift")
async def get_shift_summary(limit: int = 100):
    async with SessionLocal() as session:
        findings = (
            await session.execute(select(Finding).order_by(desc(Finding.detected_at)).limit(limit))
        ).scalars().all()
        audit = (
            await session.execute(select(AuditEntry).order_by(desc(AuditEntry.timestamp)).limit(limit))
        ).scalars().all()

    markdown = build_shift_summary(findings, audit)
    return {"markdown": markdown}


@app.post("/api/policy-template")
async def set_policy_template(payload: PolicyTemplateUpdate):
    template = payload.template.strip().lower()
    if template not in {"recommendation_only", "conservative", "default", "aggressive"}:
        raise HTTPException(400, "Invalid template")

    config.monitor.auto_remediation_profile = template
    async with SessionLocal() as session:
        session.add(
            AuditEntry(
                event_type="policy_template_changed",
                details=f"auto_remediation_profile={template}",
            )
        )
        await session.commit()
    return {"ok": True, "auto_remediation_profile": template}


@app.get("/api/anomaly")
async def get_anomaly(container_name: str | None = None):
    if not monitor:
        return {}
    return monitor.anomaly_snapshot(container_name)


@app.get("/api/risk")
async def get_risk(container_name: str | None = None):
    async with SessionLocal() as session:
        q = select(ServiceBaseline).order_by(desc(ServiceBaseline.risk_score))
        if container_name:
            q = q.where(ServiceBaseline.container_name == container_name)
        rows = (await session.execute(q)).scalars().all()
        data = [row.to_dict() for row in rows]

    if data:
        return {"containers": data, "risk_threshold": config.monitor.risk_score_threshold}

    if not monitor:
        return {"containers": [], "risk_threshold": config.monitor.risk_score_threshold}

    snapshot = monitor.risk_snapshot(container_name)
    if container_name:
        containers = [{"container_name": container_name, **snapshot}] if snapshot else []
    else:
        containers = [{"container_name": name, **payload} for name, payload in snapshot.items()]
    return {"containers": containers, "risk_threshold": config.monitor.risk_score_threshold}


@app.get("/api/ai-health")
async def get_ai_health():
    return ai_analyzer.ai_health_snapshot()


@app.get("/api/server-status")
async def get_server_status():
    started = server_started_at or datetime.utcnow()
    uptime = max(0, int((datetime.utcnow() - started).total_seconds()))
    return {
        "started_at": started.isoformat(),
        "uptime_seconds": uptime,
    }


async def _sync_risk_baselines() -> None:
    while True:
        await asyncio.sleep(10)
        if not monitor:
            continue

        snapshot = monitor.risk_snapshot()
        if not snapshot:
            continue

        async with SessionLocal() as session:
            for container_name, payload in snapshot.items():
                existing_q = select(ServiceBaseline).where(ServiceBaseline.container_name == container_name).limit(1)
                baseline = (await session.execute(existing_q)).scalar_one_or_none()
                if not baseline:
                    baseline = ServiceBaseline(container_name=container_name)

                baseline.baseline_rate = payload.get("baseline")
                baseline.drift_ratio = payload.get("drift_ratio")
                baseline.risk_score = payload.get("risk_score")
                baseline.risk_horizon_minutes = payload.get("risk_horizon_minutes")
                baseline.suspicious_count = payload.get("suspicious_count")
                baseline.reasons = json.dumps(payload.get("reasons") or [])
                baseline.updated_at = datetime.utcnow()
                session.add(baseline)

            await session.commit()
