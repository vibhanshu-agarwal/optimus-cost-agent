"""Fail-closed Python startup for the composed MAIN-5 test guard."""

from __future__ import annotations

import json
import os
from pathlib import Path

try:
    source = Path(__file__).with_name("main5_guard_impl.py")
    config_path = source.with_name("main5-config.json")
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.is_file() else {}
    original_system_root = os.environ.get("SystemRoot")
    temporary_system_root = not original_system_root and bool(config.get("system_root"))
    if temporary_system_root:
        # The accepted port guard imports Windows asyncio/socket at startup.
        # Winsock needs SystemRoot even when a product child deliberately
        # projects no system keys. Restore the child's exact env after import.
        os.environ["SystemRoot"] = config["system_root"]
    try:
        exec(compile(source.read_bytes(), str(source), "exec"), {"__name__": "_main5_guard_impl", "__file__": str(source)})
    finally:
        if temporary_system_root:
            if original_system_root is None:
                os.environ.pop("SystemRoot", None)
            else:
                os.environ["SystemRoot"] = original_system_root
except BaseException as exc:
    frame = exc.__traceback__
    while frame is not None and frame.tb_next is not None:
        frame = frame.tb_next
    function = frame.tb_frame.f_code.co_name if frame is not None else "startup"
    line = frame.tb_lineno if frame is not None else 0
    source_name = Path(frame.tb_frame.f_code.co_filename).name if frame is not None else "startup"
    error_code = getattr(exc, "winerror", None) or getattr(exc, "errno", None) or 0
    # Fixed code/type/frame location only: never render the exception value.
    os.write(2, f"MAIN5_STARTUP_FAILED:{type(exc).__name__}:{error_code}:{source_name}:{function}:{line}\n".encode("ascii"))
    os._exit(86)
