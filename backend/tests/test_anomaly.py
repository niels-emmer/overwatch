from anomaly import AnomalyScorer


def test_spike_detection_crosses_threshold() -> None:
    scorer = AnomalyScorer(anomaly_threshold=2.0)

    # Build baseline with low suspicious activity.
    scorer.evaluate(container_name="api", threshold=3, lines=["ERROR timeout"], max_level="error")
    scorer.evaluate(container_name="api", threshold=3, lines=["ERROR timeout"], max_level="error")

    res = scorer.evaluate(
        container_name="api",
        threshold=3,
        lines=["ERROR timeout", "ERROR timeout", "ERROR timeout", "ERROR timeout"],
        max_level="error",
    )

    assert res.should_emit
    assert "rate_spike" in res.reasons
    assert res.risk_score > 0


def test_novel_fingerprint_triggers_below_line_threshold() -> None:
    scorer = AnomalyScorer(anomaly_threshold=1.2)

    res = scorer.evaluate(
        container_name="worker",
        threshold=3,
        lines=["CRITICAL panic in scheduler thread"],
        max_level="critical",
    )

    assert res.suspicious_count == 1
    assert "novel_fingerprint" in res.reasons
    assert res.should_emit
    assert res.risk_horizon_minutes <= 120


def test_noise_suppression_stays_below_threshold() -> None:
    scorer = AnomalyScorer(anomaly_threshold=2.5)

    scorer.evaluate(container_name="web", threshold=3, lines=["WARNING retry soon"], max_level="warning")
    res = scorer.evaluate(container_name="web", threshold=3, lines=["WARNING retry soon"], max_level="warning")

    assert not res.should_emit
    assert res.score < 2.5
    assert res.risk_score < 65


def test_drift_detection_warns_before_threshold_burst() -> None:
    scorer = AnomalyScorer(anomaly_threshold=2.5, risk_threshold=45.0)

    # Build a stable low baseline with repeated non-novel warnings.
    scorer.evaluate(container_name="api", threshold=6, lines=["WARNING retry soon"], max_level="warning")
    scorer.evaluate(container_name="api", threshold=6, lines=["WARNING retry soon"], max_level="warning")
    scorer.evaluate(container_name="api", threshold=6, lines=["WARNING retry soon"], max_level="warning")

    # Gradual degradation: still below threshold but elevated against baseline.
    res = scorer.evaluate(
        container_name="api",
        threshold=6,
        lines=["WARNING retry soon", "WARNING retry soon", "WARNING retry soon", "WARNING retry soon"],
        max_level="warning",
    )

    assert res.suspicious_count < 6
    assert "baseline_drift" in res.reasons
    assert res.risk_score >= 45.0
    assert res.should_emit
