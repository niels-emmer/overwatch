from datetime import datetime, timedelta
import json

from action_ranking import rank_actions
from main import build_shift_summary, build_work_queue


class FakeFinding:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def to_dict(self):
        return {
            "id": self.id,
            "container_name": self.container_name,
            "severity": self.severity,
            "summary": self.summary,
            "status": self.status,
            "risk_score": self.risk_score,
            "blast_radius": json.loads(self.blast_radius) if self.blast_radius else [],
        }


class FakeAudit:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_work_queue_prioritizes_risk_then_blast_radius() -> None:
    now = datetime.now()
    low = FakeFinding(
        id="f1",
        container_name="api",
        severity="WARNING",
        summary="minor",
        status="open",
        risk_score=40.0,
        blast_radius=json.dumps(["worker"]),
        detected_at=now - timedelta(minutes=3),
    )
    high = FakeFinding(
        id="f2",
        container_name="db",
        severity="ERROR",
        summary="major",
        status="open",
        risk_score=80.0,
        blast_radius=json.dumps(["api", "worker"]),
        detected_at=now - timedelta(minutes=2),
    )

    queue = build_work_queue([low, high], now=now)
    assert queue[0]["id"] == "f2"
    assert queue[0]["priority_score"] > queue[1]["priority_score"]


def test_shift_summary_contains_required_sections() -> None:
    finding = FakeFinding(
        id="f1",
        container_name="api",
        severity="ERROR",
        summary="timeout burst",
        status="open",
        risk_score=72.0,
        blast_radius=json.dumps(["worker"]),
        detected_at=datetime.now(),
    )
    audit = [
        FakeAudit(event_type="auto_action_executed", container_name="api", details="ok", action=None),
        FakeAudit(event_type="action_policy_blocked", container_name="api", details="approval required", action=None),
    ]

    summary = build_shift_summary([finding], audit)
    assert "# Overwatch Shift Summary" in summary
    assert "## Highest Priority Incidents" in summary
    assert "## Pending Operator Actions" in summary


def test_ranked_actions_include_explainability_fields() -> None:
    actions = [
        {
            "label": "Restart API",
            "action_type": "docker_restart",
            "command": None,
            "container_name": "api",
        }
    ]

    ranked = rank_actions(actions, snapshots={}, now=datetime.now())
    assert ranked[0]["expected_effect"]
    assert ranked[0]["abort_condition"]
