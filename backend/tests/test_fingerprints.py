from fingerprints import fingerprint_log_text


def test_fingerprint_stable_for_variable_tokens() -> None:
    first = "ERROR request_id=6a1f2f7c-b782-4e74-a50b-3f4f247fa1ab from 10.2.0.15 failed in 42ms"
    second = "ERROR request_id=84992b2a-f452-4ea0-8992-cf1db16622d1 from 10.7.1.99 failed in 104ms"

    assert fingerprint_log_text(first) == fingerprint_log_text(second)


def test_fingerprint_differs_for_distinct_errors() -> None:
    timeout = "ERROR: database timeout while opening transaction"
    oom = "FATAL: process killed due to out of memory"

    assert fingerprint_log_text(timeout) != fingerprint_log_text(oom)
