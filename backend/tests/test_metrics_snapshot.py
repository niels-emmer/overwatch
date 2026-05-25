import sqlite3

from scripts.metrics_snapshot import collect_metrics


def test_collect_metrics_from_sample_db() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE findings (status TEXT)")
    conn.execute("CREATE TABLE audit_log (event_type TEXT, result TEXT)")

    conn.executemany("INSERT INTO findings(status) VALUES (?)", [("open",), ("dismissed",), ("open",)])
    conn.executemany(
        "INSERT INTO audit_log(event_type, result) VALUES (?, ?)",
        [
            ("action_executed", "done"),
            ("action_executed", "failed"),
            ("finding_detected", None),
        ],
    )

    snap = collect_metrics(conn)

    assert snap.total_findings == 3
    assert snap.open_findings == 2
    assert snap.dismissed_findings == 1
    assert snap.total_actions == 2
    assert snap.successful_actions == 1
    assert snap.failed_actions == 1
