from decimal import Decimal

from optimus.telemetry.redaction import redact_for_telemetry
from optimus.telemetry.serialization import json_safe
from optimus.telemetry.subjects import sanitize_workspace_text


def test_json_safe_converts_decimal_without_float_rounding():
    assert json_safe({"cost": Decimal("0.125")}) == {"cost": "0.125"}


def test_sanitize_workspace_text_masks_workspace_and_generic_token(tmp_path):
    text = f"token=secret-token {tmp_path / 'src' / 'optimus' / 'x.py'}"

    sanitized = sanitize_workspace_text(text, workspace_root=tmp_path)

    assert "secret-token" not in sanitized
    assert sanitized == "token=********** <workspace>/src/optimus/x.py"


def test_shared_redaction_preserves_non_secret_prose():
    assert redact_for_telemetry("token refresh logic and password reset flow") == "token refresh logic and password reset flow"


def test_sanitize_workspace_text_preserves_audit_subject_secret_masking():
    sanitized = sanitize_workspace_text("token secret-token https://user:pass@example.com/repo.git", workspace_root=None)

    assert sanitized == "token ********** https://**********@example.com/repo.git"
