"""Generate `wire_baseline_72947dba.json` (correction K5, Codex round 19 finding 5; R-13 item 1, #237 6322536508).

Runs `wire_baseline_scenarios.py`, copied unchanged from the head under test, against a clean clone of `72947dba`, and
writes the committed fixture form itself: the response bodies, with the bare-key canary replaced by `<BARE_KEY>`. The
clone's `src` and root come first on `sys.path`, and every loaded `optimus*`, `context_engine` and `tests` module is
checked to come from the clone before anything is written. Its provenance (time, interpreter, clone, arguments and
digests) is printed as one JSON line for the evidence log.

Not a test: run it by hand from the repository root, with the repository's venv python:

    <venv python> -I -B tests/unit/optimus_gateway/generate_wire_baseline.py <clone root> <output json> [<temp root>]
"""

from __future__ import annotations

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

BASELINE_HEAD = "72947dbac01f3fa521fd3a50499b2afb0cd333ae"  # pragma: allowlist secret (a public commit ID)
_OWN_PACKAGES = {"optimus", "optimus_gateway", "optimus_model_policy", "optimus_security", "context_engine", "tests"}


def main(argv: list[str]) -> int:
    started_at = datetime.now(UTC).isoformat()
    clone, output = Path(argv[1]).resolve(), Path(argv[2]).resolve()
    temp_root = Path(argv[3]).resolve() if len(argv) > 3 else None
    scenarios = Path(__file__).resolve().with_name("wire_baseline_scenarios.py")

    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    if head != BASELINE_HEAD:
        raise SystemExit(f"the clone is at {head}, not {BASELINE_HEAD}")
    if subprocess.run(["git", "-C", str(clone), "status", "--porcelain"], check=True, capture_output=True, text=True).stdout.strip():
        raise SystemExit("the clone is not clean")

    shutil.copyfile(scenarios, clone / "tests" / "unit" / "optimus_gateway" / "wire_baseline_scenarios.py")
    sys.path[:0] = [str(clone / "src"), str(clone)]
    from tests.unit.optimus_gateway import wire_baseline_scenarios as module

    with tempfile.TemporaryDirectory(dir=temp_root) as root:
        bodies = module.run_all(Path(root))
    # Checked after the run, so a module the scenarios import lazily is covered too.
    foreign = sorted(
        name
        for name, loaded in sys.modules.items()
        if name.split(".")[0] in _OWN_PACKAGES
        and getattr(loaded, "__file__", None)
        and not Path(loaded.__file__).resolve().is_relative_to(clone)
    )
    if foreign:
        raise SystemExit(f"modules loaded from outside the clone: {foreign}")
    # The fixture form: bodies only, and the canary as a placeholder, so the committed file holds no key-shaped value.
    text = json.dumps(bodies, indent=1, sort_keys=True, ensure_ascii=True).replace(module.BARE_KEY, "<BARE_KEY>") + "\n"
    output.write_bytes(text.encode("utf-8"))

    print(
        json.dumps(
            {
                "started_at": started_at,
                "finished_at": datetime.now(UTC).isoformat(),
                "interpreter": sys.executable,
                "python": platform.python_version(),
                "clone": str(clone),
                "baseline_head": head,
                "argv": argv,
                "scenarios_sha256": hashlib.sha256(scenarios.read_bytes()).hexdigest(),
                "output": str(output),
                "output_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "bodies": len(bodies),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
