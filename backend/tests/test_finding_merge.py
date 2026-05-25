from datetime import datetime, timezone
from types import SimpleNamespace

from fingerprints import merge_finding


def test_merge_finding_increments_count_and_updates_timestamp() -> None:
    existing = SimpleNamespace(
        occurrence_count=1,
        raw_logs="ERROR first",
        last_seen_at=datetime(2026, 5, 25, 19, 0, tzinfo=timezone.utc),
    )
    now = datetime(2026, 5, 25, 19, 5, tzinfo=timezone.utc)

    merge_finding(existing, "ERROR second", now)

    assert existing.occurrence_count == 2
    assert existing.last_seen_at == now
    assert "ERROR first" in existing.raw_logs
    assert "ERROR second" in existing.raw_logs


def test_merge_finding_trims_log_history() -> None:
    existing = SimpleNamespace(
        occurrence_count=2,
        raw_logs="\n".join(f"old-{i}" for i in range(6)),
        last_seen_at=datetime(2026, 5, 25, 19, 0, tzinfo=timezone.utc),
    )

    merge_finding(existing, "new-1\nnew-2", datetime.now(timezone.utc), max_log_lines=5)

    lines = existing.raw_logs.splitlines()
    assert len(lines) == 5
    assert lines[-2:] == ["new-1", "new-2"]
