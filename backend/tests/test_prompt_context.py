from prompt_context import build_context_block, redact_text


def test_context_assembly_contains_expected_fields() -> None:
    context = {
        "container": {"name": "api", "status": "running", "image": "api:latest"},
        "peer_containers": ["db", "worker"],
        "recent_error_lines": ["ERROR timeout"],
    }

    block = build_context_block(context)

    assert '"container"' in block
    assert '"peer_containers"' in block
    assert '"recent_error_lines"' in block


def test_context_budget_enforcement() -> None:
    context = {
        "recent_error_lines": ["x" * 400 for _ in range(30)],
        "peer_recent_logs": {"db": ["y" * 400 for _ in range(30)]},
    }

    block = build_context_block(context, max_chars=500)

    assert len(block) <= 503


def test_redaction_masks_secret_like_tokens() -> None:
    text = "password=mysecret token=abc123 api_key=topsecret"
    redacted = redact_text(text)

    assert "mysecret" not in redacted
    assert "abc123" not in redacted
    assert "topsecret" not in redacted
    assert "<redacted>" in redacted
