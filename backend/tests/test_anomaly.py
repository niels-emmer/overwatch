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


def test_noise_suppression_stays_below_threshold() -> None:
    scorer = AnomalyScorer(anomaly_threshold=2.5)

    scorer.evaluate(container_name="web", threshold=3, lines=["WARNING retry soon"], max_level="warning")
    res = scorer.evaluate(container_name="web", threshold=3, lines=["WARNING retry soon"], max_level="warning")

    assert not res.should_emit
    assert res.score < 2.5
