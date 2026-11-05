"""Plan 12.10 Task 2: the real configured artifact, through the real setup's layout and digest check, loaded with the network refused.

Selected with `-m requires_plan12_index_redis`; needs no container. P1210_ARTIFACT_SNAPSHOT names the released local copy of the artifact,
and nothing here downloads one.
"""

from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from optimus.acp.memory_setup import run_setup, shipped_defaults
from optimus_security.memory_index_config import memory_index_root
from tests.unit.acp.conftest import FakeKeyring

pytestmark = [pytest.mark.requires_plan12_index_redis]

_NO_NETWORK = """
import json, socket, sys
from pathlib import Path

def refuse(*_args, **_kwargs):
    raise OSError("the network was attempted")

socket.socket.connect = socket.socket.connect_ex = socket.create_connection = socket.getaddrinfo = refuse

from optimus.context.memory_workspace import FastembedEmbedder
from optimus_security.memory_index_config import read

root, directory = Path(sys.argv[1]), sys.argv[2]
_literal, config, _refusal = read(root)
vectors = FastembedEmbedder(root, config.embedding, directory=directory).embed(["open a file", "read a file", "banana bread recipe"])
print(json.dumps({"dimensions": config.embedding.dimensions, "lengths": [len(vector) for vector in vectors], "vectors": [list(vector) for vector in vectors]}))
"""


def test_the_configured_artifact_loads_through_setup_with_the_network_refused(tmp_path: Path) -> None:
    snapshot = os.environ.get("P1210_ARTIFACT_SNAPSHOT")
    if not snapshot or not Path(snapshot).is_dir():
        pytest.skip("UNRUN: P1210_ARTIFACT_SNAPSHOT names no local artifact")

    def copy(*, repository: str, revision: str, target: Path) -> None:
        shutil.copytree(snapshot, target, dirs_exist_ok=True)

    defaults = shipped_defaults()
    run_setup(tmp_path, keyring_backend=FakeKeyring(), confirm=lambda _description: True, download=copy, defaults=defaults)  # checks the real digest
    root = memory_index_root(tmp_path)
    result = subprocess.run([sys.executable, "-c", _NO_NETWORK, str(root), defaults["embedding"]["artifact_directory"]], capture_output=True, text=True, check=False, timeout=180)
    assert result.returncode == 0, result.stderr[-2000:]
    reply = json.loads(result.stdout.strip().splitlines()[-1])
    assert reply["lengths"] == [reply["dimensions"] * 4] * 3

    def cosine(left: list[int], right: list[int]) -> float:
        a = struct.unpack(f"<{reply['dimensions']}f", bytes(left))
        b = struct.unpack(f"<{reply['dimensions']}f", bytes(right))
        return sum(x * y for x, y in zip(a, b, strict=True)) / (sum(x * x for x in a) * sum(y * y for y in b)) ** 0.5

    near, far = cosine(reply["vectors"][0], reply["vectors"][1]), cosine(reply["vectors"][0], reply["vectors"][2])
    assert near > far
