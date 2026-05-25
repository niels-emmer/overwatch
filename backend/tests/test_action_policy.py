from action_policy import classify_risk, evaluate_policy


def test_risk_classification() -> None:
    assert classify_risk("docker_restart", None) == "low"
    assert classify_risk("docker_exec", "rm -rf /tmp/foo") == "high"
    assert classify_risk("docker_exec", "chmod 755 /app/start.sh") == "medium"


def test_deny_high_risk_without_approval() -> None:
    decision = evaluate_policy("docker_exec", "rm -rf /", high_risk_approved=False)

    assert not decision.allowed
    assert decision.reason == "HIGH_RISK_APPROVAL_REQUIRED"


def test_allow_high_risk_with_approval() -> None:
    decision = evaluate_policy("docker_exec", "rm -rf /tmp/safe", high_risk_approved=True)

    assert decision.allowed
    assert decision.risk == "high"
