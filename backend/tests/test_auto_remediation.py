from datetime import datetime, timedelta

import main


def test_auto_profile_enabled() -> None:
    original = main.config.monitor.auto_remediation_profile
    try:
        main.config.monitor.auto_remediation_profile = "conservative"
        assert main._auto_profile_enabled()

        main.config.monitor.auto_remediation_profile = "recommendation_only"
        assert not main._auto_profile_enabled()
    finally:
        main.config.monitor.auto_remediation_profile = original


def test_auto_rate_limit_window() -> None:
    container = "api"
    original_window = main.config.monitor.auto_remediation_window_minutes
    original_max = main.config.monitor.auto_remediation_max_per_window
    history = main._AUTO_HISTORY[container]
    snapshot = list(history)

    try:
        main.config.monitor.auto_remediation_window_minutes = 30
        main.config.monitor.auto_remediation_max_per_window = 2
        history.clear()

        assert main._can_auto_remediate_now(container)
        history.append(datetime.utcnow())
        assert main._can_auto_remediate_now(container)
        history.append(datetime.utcnow())
        assert not main._can_auto_remediate_now(container)

        history.clear()
        history.append(datetime.utcnow() - timedelta(minutes=31))
        assert main._can_auto_remediate_now(container)
    finally:
        history.clear()
        history.extend(snapshot)
        main.config.monitor.auto_remediation_window_minutes = original_window
        main.config.monitor.auto_remediation_max_per_window = original_max
