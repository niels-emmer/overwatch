from datetime import datetime

from correlation import correlate_incident


def test_correlation_reuses_existing_group_for_same_stack() -> None:
    result = correlate_incident(
        container_name="stack-api-1",
        fingerprint="abc123",
        trigger_reasons=["rate_spike"],
        peer_containers=["stack-worker-1"],
        candidate_groups=[("inc-existing", "stack-db-1", datetime.now())],
    )

    assert result.incident_group == "inc-existing"
    assert result.confidence >= 0.7
    assert "same_stack:stack" in result.evidence


def test_blast_radius_inference_uses_peers() -> None:
    result = correlate_incident(
        container_name="stack-api-1",
        fingerprint="xyz987",
        trigger_reasons=["novel_fingerprint"],
        peer_containers=["stack-worker-1", "stack-db-1", "stack-api-1"],
        candidate_groups=[],
    )

    assert result.incident_group.startswith("inc-")
    assert result.blast_radius == ["stack-db-1", "stack-worker-1"]
    assert any(item.startswith("peer_impact:") for item in result.evidence)
