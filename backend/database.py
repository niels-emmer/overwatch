import os
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, Integer, text, func
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

os.makedirs("/app/data", exist_ok=True) if os.path.exists("/app") else os.makedirs(
    os.path.join(os.path.dirname(__file__), "..", "data"), exist_ok=True
)

_db_path = "/app/data/overwatch.db" if os.path.exists("/app") else os.path.join(
    os.path.dirname(__file__), "..", "data", "overwatch.db"
)
DATABASE_URL = f"sqlite+aiosqlite:///{_db_path}"

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    container_name: Mapped[str] = mapped_column(String)
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    severity: Mapped[str] = mapped_column(String)
    summary: Mapped[str] = mapped_column(Text)
    root_cause: Mapped[str] = mapped_column(Text, nullable=True)
    raw_logs: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="open")
    fingerprint: Mapped[str] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    anomaly_score: Mapped[float] = mapped_column(nullable=True)
    trigger_reasons: Mapped[str] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        import json

        return {
            "id": self.id,
            "container_name": self.container_name,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "severity": self.severity,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "raw_logs": self.raw_logs,
            "status": self.status,
            "fingerprint": self.fingerprint,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "occurrence_count": self.occurrence_count or 1,
            "anomaly_score": self.anomaly_score,
            "trigger_reasons": json.loads(self.trigger_reasons) if self.trigger_reasons else [],
        }


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    finding_id: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    steps: Mapped[str] = mapped_column(Text)
    proposed_actions: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String, default="pending")

    def to_dict(self) -> dict:
        import json
        return {
            "id": self.id,
            "finding_id": self.finding_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "steps": json.loads(self.steps) if self.steps else [],
            "proposed_actions": json.loads(self.proposed_actions) if self.proposed_actions else [],
            "status": self.status,
        }


class AuditEntry(Base):
    __tablename__ = "audit_log"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    event_type: Mapped[str] = mapped_column(String)
    container_name: Mapped[str] = mapped_column(String, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=True)
    result: Mapped[str] = mapped_column(String, nullable=True)
    details: Mapped[str] = mapped_column(Text, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "container_name": self.container_name,
            "action": self.action,
            "result": self.result,
            "details": self.details,
        }


class IncidentOutcome(Base):
    __tablename__ = "incident_outcomes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    fingerprint: Mapped[str] = mapped_column(String)
    container_name: Mapped[str] = mapped_column(String)
    action_type: Mapped[str] = mapped_column(String)
    action_signature: Mapped[str] = mapped_column(String)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    timeout_count: Mapped[int] = mapped_column(Integer, default=0)
    abort_count: Mapped[int] = mapped_column(Integer, default=0)
    last_status: Mapped[str] = mapped_column(String, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "fingerprint": self.fingerprint,
            "container_name": self.container_name,
            "action_type": self.action_type,
            "action_signature": self.action_signature,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "timeout_count": self.timeout_count,
            "abort_count": self.abort_count,
            "last_status": self.last_status,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
        }


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_findings(conn)


async def _migrate_findings(conn) -> None:
    # Lightweight migration support for SQLite deployments without alembic.
    result = await conn.execute(text("PRAGMA table_info(findings)"))
    columns = {row[1] for row in result.fetchall()}

    if "fingerprint" not in columns:
        await conn.execute(text("ALTER TABLE findings ADD COLUMN fingerprint VARCHAR"))
    if "first_seen_at" not in columns:
        await conn.execute(text("ALTER TABLE findings ADD COLUMN first_seen_at DATETIME"))
    if "last_seen_at" not in columns:
        await conn.execute(text("ALTER TABLE findings ADD COLUMN last_seen_at DATETIME"))
    if "occurrence_count" not in columns:
        await conn.execute(text("ALTER TABLE findings ADD COLUMN occurrence_count INTEGER DEFAULT 1"))
    if "anomaly_score" not in columns:
        await conn.execute(text("ALTER TABLE findings ADD COLUMN anomaly_score FLOAT"))
    if "trigger_reasons" not in columns:
        await conn.execute(text("ALTER TABLE findings ADD COLUMN trigger_reasons TEXT"))

    await conn.execute(text("UPDATE findings SET occurrence_count = 1 WHERE occurrence_count IS NULL"))
    await conn.execute(text("UPDATE findings SET first_seen_at = detected_at WHERE first_seen_at IS NULL"))
    await conn.execute(text("UPDATE findings SET last_seen_at = detected_at WHERE last_seen_at IS NULL"))
