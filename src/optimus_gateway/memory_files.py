"""What files the memory store's data directory holds, for a purge's disk step (Plan 12.11; Codex CP2 review 1, finding 2).

Redis reports a rewrite and a snapshot as done even when it could not delete an old AOF file, so counters alone never prove
that purged text left the declared boundary. After both have run, the directory must hold only what the current AOF manifest
names (no history file), the snapshot and the AOF directory: anything else may still hold the text, and the purge stays
pending. The inventory is read through the local Docker engine from the provisioned container, which must carry the
configured resource label and publish the configured port.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

from optimus_security.memory_store_config import MemoryStoreConfig

RESOURCE_LABEL: Final = "optimus.memory.resource"  # the label local_infra puts on the container it provisions
_DATA: Final = "/data"
_AOF_DIR: Final = "appendonlydir"
_SNAPSHOT: Final = "dump.rdb"
_SEPARATOR: Final = "--optimus-inventory--"


@dataclass(frozen=True)
class Inventory:
    top: tuple[str, ...]  # entries directly under the data directory
    aof: tuple[str, ...]  # entries in the AOF directory
    manifest: str  # the AOF manifest's text


class InventoryUnavailable(Exception):
    """The files could not be listed: the disk step cannot be shown complete."""


def residue(inventory: Inventory) -> str | None:
    """Why the files may still hold deleted text, or None when they hold only the current snapshot and AOF set."""
    if set(inventory.top) - {_SNAPSHOT, _AOF_DIR}:
        return "unexpected_files"  # a leftover temporary snapshot or rewrite file
    listed: set[str] = set()
    for line in inventory.manifest.splitlines():
        fields = line.split()
        if not fields:
            continue
        entry = dict(zip(fields[::2], fields[1::2], strict=False))
        if "file" not in entry or entry.get("type") not in ("b", "i", "h"):
            return "manifest_unreadable"
        if entry["type"] == "h":
            return "history_files"  # Redis kept a superseded file in its manifest
        listed.add(entry["file"])
    if not listed:
        return "manifest_unreadable"
    manifests = {name for name in inventory.aof if name.endswith(".manifest")}
    if len(manifests) != 1 or set(inventory.aof) - manifests - listed:
        return "retained_files"  # an old base or increment the rewrite left behind
    return None


def parse(output: str) -> Inventory:
    parts = output.split(_SEPARATOR + "\n")
    if len(parts) != 3:
        raise InventoryUnavailable("unparsable listing")
    top, aof, manifest = parts
    return Inventory(tuple(top.split()), tuple(aof.split()), manifest)


def docker_inventory(config: MemoryStoreConfig) -> Callable[[float], Inventory]:
    """An inventory of the provisioned container's data directory, read with `docker exec`, each step within `timeout`."""

    def read(timeout: float) -> Inventory:
        docker = shutil.which("docker")
        if docker is None:
            raise InventoryUnavailable("docker not found")
        try:
            view = subprocess.run([docker, "inspect", "--type", "container", config.container],
                                  capture_output=True, text=True, check=False, timeout=timeout)
            details = json.loads(view.stdout)[0] if view.returncode == 0 else None
            if details is None or (details.get("Config") or {}).get("Labels", {}).get(RESOURCE_LABEL) != config.resource:
                raise InventoryUnavailable("not the provisioned container")
            bindings = (details.get("HostConfig") or {}).get("PortBindings") or {}
            if not any(str(binding.get("HostPort")) == str(config.port) for spec in bindings.values() for binding in spec or ()):
                raise InventoryUnavailable("container does not publish the configured port")
            script = (f"ls -1A {_DATA} && echo {_SEPARATOR} && ls -1A {_DATA}/{_AOF_DIR} && echo {_SEPARATOR} && "
                      f"cat {_DATA}/{_AOF_DIR}/*.manifest")
            listing = subprocess.run([docker, "exec", config.container, "sh", "-c", script],
                                     capture_output=True, text=True, check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError, AttributeError) as exc:
            raise InventoryUnavailable(type(exc).__name__) from None
        if listing.returncode != 0:
            raise InventoryUnavailable("listing failed")
        return parse(listing.stdout)

    return read
