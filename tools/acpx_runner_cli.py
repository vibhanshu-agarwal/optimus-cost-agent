"""Shared executable lookup and version probe for the FU-9 and FU-10 runners."""

from __future__ import annotations

import shutil
import subprocess


def resolve_acpx(not_found_error: type[RuntimeError]) -> str:
    acpx = shutil.which("acpx")
    if acpx is None:
        raise not_found_error(
            "acpx not found on PATH. Install the independent acpx ACP client "
            "(https://github.com/openclaw/acpx); never substitute a project client."
        )
    return acpx


def acpx_version(acpx: str, evidence_error: type[ValueError]) -> str:
    completed = subprocess.run(  # noqa: S603
        [acpx, "--version"],
        capture_output=True,
        text=True,
        check=False,
        shell=False,
        timeout=30,
    )
    if completed.returncode != 0:
        raise evidence_error("acpx --version failed")
    version = (completed.stdout or completed.stderr or "").strip()
    if not version:
        raise evidence_error("acpx --version returned empty output")
    return version
