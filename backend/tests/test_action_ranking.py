from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from action_ranking import OutcomeSnapshot, action_signature, classify_outcome, rank_actions
from database import Base, IncidentOutcome
from main import _load_outcome_snapshots, _record_incident_outcome


@pytest.mark.asyncio
async def test_outcome_persistence_and_snapshot_loading() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sig = action_signature("docker_restart", "api", None)

    async with Session() as session:
        await _record_incident_outcome(
            session,
            fingerprint="fp-123",
            container_name="api",
            action_type="docker_restart",
            action_sig=sig,
            outcome_status="success",
        )
        await session.commit()

        row = (
            await session.execute(
                select(IncidentOutcome).where(
                    IncidentOutcome.fingerprint == "fp-123",
                    IncidentOutcome.container_name == "api",
                )
            )
        ).scalar_one()

        assert row.success_count == 1
        assert row.failure_count == 0

        snapshots = await _load_outcome_snapshots(session, "fp-123", "api")
        assert sig in snapshots
        assert snapshots[sig].success_count == 1

    await engine.dispose()


def test_rank_actions_prefers_higher_success_history() -> None:
    restart_sig = action_signature("docker_restart", "api", None)
    exec_sig = action_signature("docker_exec", "api", "echo health")

    actions = [
        {
            "label": "Health probe",
            "action_type": "docker_exec",
            "command": "echo health",
            "container_name": "api",
        },
        {
            "label": "Restart container",
            "action_type": "docker_restart",
            "command": None,
            "container_name": "api",
        },
    ]

    snapshots = {
        exec_sig: OutcomeSnapshot(1, 4, 0, 0, datetime.now()),
        restart_sig: OutcomeSnapshot(6, 1, 0, 0, datetime.now()),
    }

    ranked = rank_actions(actions, snapshots, now=datetime.now())

    assert ranked[0]["action_type"] == "docker_restart"
    assert ranked[0]["historical_sample_size"] == 7
    assert ranked[0]["ranking_reason"]


def test_classify_outcome_timeout_and_abort() -> None:
    assert classify_outcome("failed", "Request timeout after 30s") == "timeout"
    assert classify_outcome("failed", "Operator abort requested") == "abort"
    assert classify_outcome("done", "ok") == "success"
