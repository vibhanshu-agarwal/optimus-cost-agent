"""Static-analysis tests for the manual gateway launcher scripts.

Plan 9.96, Task 5 Batch 3 Step 4: `tools/run_local_gateway.sh`/`.ps1` must
stop sourcing/executing the repository-controlled `.env.gateway` and instead
delegate to `optimus-trust run-gateway`, which parses it as untrusted DATA
(never `source`d/executed, never copied into the invoking shell's own
environment). A script that still does `source .env.gateway` or
`. .env.gateway` anywhere — including a fallback branch or a comment-adjacent
line — reopens the exact hole this task closes: sourcing executes arbitrary
shell content from a file this plan treats as untrusted input.
"""

from __future__ import annotations

import re
from pathlib import Path

_SH_SCRIPT = Path("tools/run_local_gateway.sh")
_PS1_SCRIPT = Path("tools/run_local_gateway.ps1")


class TestBashLauncherNeverSourcesEnvGateway:
    def test_script_exists(self) -> None:
        assert _SH_SCRIPT.is_file()

    def test_script_never_sources_env_gateway_anywhere(self) -> None:
        """No `source .env.gateway`, no `. .env.gateway` (POSIX dot form),
        and no `source "${ENV_FILE}"` / `. "${ENV_FILE}"` where ENV_FILE
        points at .env.gateway — checked structurally, not just by grepping
        the literal filename, since a dot-sourced ENV_FILE variable is the
        same hole under a different name."""
        text = _SH_SCRIPT.read_text(encoding="utf-8")
        # No bare `source` or POSIX `.` sourcing command anywhere in the file.
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            assert not re.match(r"^source\s", stripped), f"found `source` command: {line!r}"
            assert not re.match(r"^\.\s+\S", stripped), f"found POSIX dot-sourcing command: {line!r}"

    def test_script_does_not_reference_env_file_variable_at_all(self) -> None:
        """The old ENV_FILE variable (used only to source the file) must be
        gone entirely, not merely unsourced -- its presence would indicate
        the script still reads .env.gateway content into shell variables
        some other way."""
        text = _SH_SCRIPT.read_text(encoding="utf-8")
        assert "ENV_FILE" not in text or "source" not in text

    def test_script_delegates_to_optimus_trust_run_gateway(self) -> None:
        text = _SH_SCRIPT.read_text(encoding="utf-8")
        assert "optimus-trust" in text
        assert "run-gateway" in text

    def test_script_no_longer_invokes_optimus_gateway_module_directly(self) -> None:
        """The script must not itself construct the optimus_gateway child
        process (e.g. `python -m optimus_gateway`) -- that construction,
        including the signed manifest and explicit bind args, is
        optimus-trust run-gateway's job now."""
        text = _SH_SCRIPT.read_text(encoding="utf-8")
        assert "-m optimus_gateway" not in text

    def test_script_still_checks_env_gateway_file_presence_before_delegating(self) -> None:
        """A missing .env.gateway should still produce a clear message
        before delegating -- optimus-trust run-gateway also checks this,
        but a fast pre-check keeps the script's own error message specific
        to the manual-launch context."""
        text = _SH_SCRIPT.read_text(encoding="utf-8")
        assert ".env.gateway" in text


class TestPowershellLauncherNeverCopiesEnvGatewayIntoSession:
    def test_script_exists(self) -> None:
        assert _PS1_SCRIPT.is_file()

    def test_script_no_longer_parses_env_gateway_into_variables(self) -> None:
        """The old Read-DotEnvFile helper (and any SetEnvironmentVariable
        CALL, as opposed to a comment mentioning it) must be gone -- copying
        .env.gateway values into the invoking PowerShell session's
        environment is the same class of hole `source` is in bash:
        repository-controlled content ends up live in the operator's own
        shell. Checked against non-comment lines only, since a comment
        explaining WHY the script no longer does this legitimately mentions
        the API name."""
        text = _PS1_SCRIPT.read_text(encoding="utf-8")
        assert "Read-DotEnvFile" not in text
        non_comment_lines = [
            line for line in text.splitlines() if not line.strip().startswith("#")
        ]
        assert not any("SetEnvironmentVariable" in line for line in non_comment_lines)

    def test_script_delegates_to_optimus_trust_run_gateway(self) -> None:
        text = _PS1_SCRIPT.read_text(encoding="utf-8")
        assert "optimus-trust" in text
        assert "run-gateway" in text

    def test_script_no_longer_invokes_optimus_gateway_module_directly(self) -> None:
        text = _PS1_SCRIPT.read_text(encoding="utf-8")
        assert "-m optimus_gateway" not in text

    def test_script_still_checks_env_gateway_file_presence_before_delegating(self) -> None:
        text = _PS1_SCRIPT.read_text(encoding="utf-8")
        assert ".env.gateway" in text
