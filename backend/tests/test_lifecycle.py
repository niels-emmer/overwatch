from lifecycle import is_valid_transition, status_after_successful_action, status_for_regression


def test_transition_rules() -> None:
    assert is_valid_transition("open", "investigating")
    assert is_valid_transition("mitigated", "resolved")
    assert not is_valid_transition("dismissed", "open")


def test_successful_action_marks_mitigated() -> None:
    assert status_after_successful_action("open") == "mitigated"
    assert status_after_successful_action("investigating") == "mitigated"


def test_regression_reopen_rules() -> None:
    assert status_for_regression("resolved") == "regressed"
    assert status_for_regression("mitigated") == "regressed"
    assert status_for_regression("open") is None
