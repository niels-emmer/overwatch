from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricsSnapshot:
    total_findings: int
    open_findings: int
    dismissed_findings: int
    total_actions: int
    successful_actions: int
    failed_actions: int


def _scalar(conn: sqlite3.Connection, query: str) -> int:
    row = conn.execute(query).fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def collect_metrics(conn: sqlite3.Connection) -> MetricsSnapshot:
    total_findings = _scalar(conn, "SELECT COUNT(*) FROM findings")
    open_findings = _scalar(conn, "SELECT COUNT(*) FROM findings WHERE status = 'open'")
    dismissed_findings = _scalar(conn, "SELECT COUNT(*) FROM findings WHERE status = 'dismissed'")
    total_actions = _scalar(conn, "SELECT COUNT(*) FROM audit_log WHERE event_type = 'action_executed'")
    successful_actions = _scalar(conn, "SELECT COUNT(*) FROM audit_log WHERE event_type = 'action_executed' AND result = 'done'")
    failed_actions = _scalar(conn, "SELECT COUNT(*) FROM audit_log WHERE event_type = 'action_executed' AND result = 'failed'")

    return MetricsSnapshot(
        total_findings=total_findings,
        open_findings=open_findings,
        dismissed_findings=dismissed_findings,
        total_actions=total_actions,
        successful_actions=successful_actions,
        failed_actions=failed_actions,
    )


def print_metrics(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        snap = collect_metrics(conn)
    finally:
        conn.close()

    print(f"total_findings={snap.total_findings}")
    print(f"open_findings={snap.open_findings}")
    print(f"dismissed_findings={snap.dismissed_findings}")
    print(f"total_actions={snap.total_actions}")
    print(f"successful_actions={snap.successful_actions}")
    print(f"failed_actions={snap.failed_actions}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Print Overwatch baseline metrics from SQLite DB")
    parser.add_argument("db_path", help="Path to overwatch.db")
    args = parser.parse_args()

    print_metrics(args.db_path)
