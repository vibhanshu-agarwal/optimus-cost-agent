"""What files the memory store's data directory holds, for a purge's disk step (Plan 12.11; Codex CP2 review 1, finding 2).

Redis reports a rewrite and a snapshot as done even when it could not delete an old AOF file, so counters alone never prove
that purged text left the declared boundary. After both have run, the directory must hold only what the current AOF manifest
names (no history file), the snapshot and the AOF directory: anything else may still hold the text, and the purge stays
pending. The inventory is read through the local Docker engine from the provisioned container, which must carry the
configured resource label and publish the configured port.

A fork killed mid-run leaves its temporary file behind, and Redis never removes another process's (found on the real store
in the CP2 rerun on 1051ae5): a purge after such a crash would stay pending forever. So files Redis itself names and no longer
uses are removed by the Gateway, while no fork runs: see `abandoned`.
"""

from __future__ import annotations

import json
import re
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
_REDIS_TEMP: Final = re.compile(r"temp-\d+\.rdb|temp-rewriteaof-(bg-)?\d+\.aof")  # a snapshot or rewrite fork's working file
_AOF_PART: Final = re.compile(r"(?P<prefix>[A-Za-z0-9._-]+)\.\d+\.(base\.(rdb|aof)|incr\.aof)")


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


def abandoned(inventory: Inventory) -> tuple[str, ...]:
    """Files under the data directory that Redis itself names and no longer uses: a fork's temporary snapshot or rewrite, and
    AOF parts the manifest no longer lists. A part outside the manifest is never in use: Redis lists a new increment before
    writing to it and renames a new base in with the manifest. Removing a running fork's temporary file only fails that fork,
    which the next disk step reissues; so the caller removes these only while no fork runs. Anything else stays residue."""
    listed = {fields[fields.index("file") + 1] for fields in map(str.split, inventory.manifest.splitlines())
              if "file" in fields[:-1]}
    prefixes = {match["prefix"] for name in listed if (match := _AOF_PART.fullmatch(name))}
    found = [name for name in inventory.top if _REDIS_TEMP.fullmatch(name)]
    found += [f"{_AOF_DIR}/{name}" for name in inventory.aof
              if name not in listed and (match := _AOF_PART.fullmatch(name)) and match["prefix"] in prefixes]
    return tuple(found)


def parse(output: str) -> Inventory:
    parts = output.split(_SEPARATOR + "\n")
    if len(parts) != 3:
        raise InventoryUnavailable("unparsable listing")
    top, aof, manifest = parts
    return Inventory(tuple(top.split()), tuple(aof.split()), manifest)


def docker_inventory(config: MemoryStoreConfig) -> Callable[[float, tuple[str, ...]], Inventory]:
    """An inventory of the provisioned container's data directory, read with `docker exec`, each step within `timeout`. The
    `remove` paths (relative to the data directory, from `abandoned`) are deleted first, passed as arguments, never as script."""

    def read(timeout: float, remove: tuple[str, ...]) -> Inventory:
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
            script = (f'cd {_DATA} && {{ [ "$#" -eq 0 ] || rm -f -- "$@"; }} && ls -1A {_DATA} && echo {_SEPARATOR} && '
                      f"ls -1A {_DATA}/{_AOF_DIR} && echo {_SEPARATOR} && cat {_DATA}/{_AOF_DIR}/*.manifest")
            listing = subprocess.run([docker, "exec", config.container, "sh", "-c", script, "sh", *remove],
                                     capture_output=True, text=True, check=False, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired, ValueError, IndexError, TypeError, AttributeError) as exc:
            raise InventoryUnavailable(type(exc).__name__) from None
        if listing.returncode != 0:
            raise InventoryUnavailable("listing failed")
        return parse(listing.stdout)

    return read
