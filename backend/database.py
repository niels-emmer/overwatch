import os
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, Text, func
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "container_name": self.container_name,
            "detected_at": self.detected_at.isoformat() if self.detected_at else None,
            "severity": self.severity,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "raw_logs": self.raw_logs,
            "status": self.status,
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


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
