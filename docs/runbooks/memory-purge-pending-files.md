# Memory purge held pending by the data directory

A memory purge completes only when the memory store's data directory holds nothing but Redis's current snapshot and AOF
set. When anything else is there, the Gateway leaves the purge `pending` and its `purge_status` reply says why:

```json
{"purge_state": "pending", "files": "unexpected_files", "blocking": ["temp-4242.rdb"], "next": "inspect_data_files",
 "runbook": "docs/runbooks/memory-purge-pending-files.md"}
```

The Gateway never removes a file itself, because no listing can prove a file is one Redis made and has finished with. That
check is yours, and this runbook is how you do it. Until a blocking file is gone it may still hold the purged text.

## 1. Find the store's container

The non-secret store facts are in `<config_root>/memory-store/memory-store.json`. Read `container`, `resource` and `port`
from it. Then confirm that the container is the one Optimus provisioned. Both commands only read:

```bash
docker inspect --format '{{index .Config.Labels "optimus.memory.resource"}} {{.State.StartedAt}}' <container>
```

The label must equal `resource`. Note `StartedAt`, which is when the current Redis started. If the label is different,
stop: this is not the store's container.

## 2. Look at what is there

```bash
docker exec <container> find /data -mindepth 1 -maxdepth 2 -printf '%y %s %TY-%Tm-%TdT%TT %P\n'
```

```bash
docker exec <container> sh -c 'cat /data/appendonlydir/*.manifest'
```

Every name in `blocking` is relative to `/data`. Act only on those names, one at a time, with no wildcards.

## 3. Decide, by reason

| `files` | What it means | What to do |
|---|---|---|
| `unexpected_files` | A name other than `dump.rdb` and `appendonlydir` at the top, or something that is not a regular file. `temp-<pid>.rdb`, `temp-rewriteaof-<pid>.aof` and `temp-rewriteaof-bg-<pid>.aof` are a snapshot's or rewrite's working files, which a Redis killed mid-fork leaves behind. | A working file is retired when its modification time is before `StartedAt` (the current Redis never opened it), or when `docker exec <container> cat /proc/<pid>/cmdline` shows no Redis process with that pid. Then remove exactly that file: `docker exec <container> rm -- /data/<name>`. Do not remove anything else this way: find out what wrote it, since it may hold memory text, and dispose of it as you would that text. |
| `retained_files` | A file in `appendonlydir` that the manifest does not name: an old base or increment the rewrite could not delete. | Check that the manifest from step 2 does not list it, and that it is older than the manifest. Then remove exactly that file. |
| `history_files` | The manifest still lists a superseded file. Redis deletes these itself after a rewrite. | Wait a minute and ask again. If it stays, read `docker logs <container>` for the delete error and fix its cause (permissions or disk). Never edit the manifest. |
| `manifest_unreadable` | The manifest is not one Redis writes: a malformed line, no base or two, increments out of sequence, a name that does not match its type or sequence, or a listed file that is missing. | Do not edit or remove anything. Keep a copy of the manifest and the listing, and report it. The purge stays pending. |
| `file_inventory_unavailable` | The Gateway could not list the directory: Docker is not reachable, the container lacks the label or does not publish the configured port, or the listing failed or was malformed. | Fix the cause from step 1. Nothing in `/data` is changed. |

## 4. Check again

Ask for the same item's `purge_status` again, as whatever requested the purge does when it retries. The Gateway reads the
directory again, and the purge completes once nothing blocks it. Nothing needs restarting. A Redis restart is safe but
not needed: it only makes the disk step start over with a fresh rewrite and snapshot.
