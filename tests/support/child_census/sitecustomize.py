"""Child census hook: which Python children of an ordinary pytest run ask for the real known folders?

Test support only, and inert unless a census asks for it: it does nothing without
`OPTIMUS_TEST_CHILD_CENSUS_DIR`. A census run puts this folder on PYTHONPATH for one ordinary
pytest invocation; nothing is installed in the environment and no launcher is changed.

In each Python child that inherits that environment it records a start line, arms the same refusal
as `tests.support.child_tripwire` on the product's real Windows known-folder adapter, and records an
end line. A child that asks for the real folders is refused and recorded; the real folders are
never resolved. Each line carries the test pytest was running when the child started. In the launching process
it also records every `subprocess.Popen` with the test frame it came from and whether the child's
environment still carries this hook, so a site is credited only by its own launches. Where the
MAIN-5 guard is active the hook stands aside. A failure here never changes the observed process.
"""

import os
import sys

_directory = os.environ.get("OPTIMUS_TEST_CHILD_CENSUS_DIR")
_TARGET = "optimus.acp.trusted_paths"
REFUSAL = "TEST_CHILD_CENSUS_REAL_ADAPTER"

if _directory and not getattr(sys, "_main5_guard_activated", False):
    try:
        import atexit
        import importlib.util
        import json

        _file = os.path.join(_directory, f"{os.getpid()}-{os.urandom(3).hex()}.jsonl")
        _test = os.environ.get("PYTEST_CURRENT_TEST", "")[:300]
        _calls = [0]

        def _note(event, **fields):
            try:
                with open(_file, "a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"event": event, "pid": os.getpid(), "test": _test, **fields}) + "\n")
            except OSError:
                pass

        def _refuse():
            _calls[0] += 1
            _note("real_adapter_call", count=_calls[0])
            raise RuntimeError(REFUSAL)

        class _Finder:
            busy = False

            def find_spec(self, name, path=None, target=None):
                if name != _TARGET or self.busy:
                    return None
                self.busy = True
                try:
                    spec = importlib.util.find_spec(name)
                finally:
                    self.busy = False
                if spec is None or spec.loader is None:
                    return None
                execute = spec.loader.exec_module

                def exec_module(module):
                    execute(module)
                    # A pytest session installs its own guard on this adapter (its conftest imports the
                    # guard module first); leave that one alone. Any other process is armed, whether
                    # or not it happens to import pytest.
                    if "tools.testing.run_context_guard" not in sys.modules:
                        module._real_windows_known_folders = _refuse
                    _note("trusted_paths_imported")

                spec.loader.exec_module = exec_module
                return spec

        sys.meta_path.insert(0, _Finder())

        def _launch_site():
            frame = sys._getframe(2)
            while frame is not None:
                name = frame.f_code.co_filename.replace("\\", "/")
                marker = name.find("/tests/")
                if marker >= 0 and "/tests/support/child_census/" not in name:
                    return name[marker + 1:], frame.f_code.co_name, frame.f_lineno
                frame = frame.f_back
            return None, None, None

        def _audit(event, arguments):
            # The launching side: which test frame started a child, and whether the child's
            # environment still carries this hook. Recorded before the child exists.
            if event != "subprocess.Popen":
                return
            try:
                executable, launch_arguments, _cwd, env = arguments
                effective = os.environ if env is None else env
                hooked = bool(effective.get("OPTIMUS_TEST_CHILD_CENSUS_DIR")) and "child_census" in str(effective.get("PYTHONPATH", ""))
                file, function, line = _launch_site()
                program = executable or (launch_arguments[0] if launch_arguments else "")
                _note("launch", site_file=file, site_function=function, site_line=line,
                      hook_env=hooked, program=os.path.basename(str(program))[:80],
                      launching_test=os.environ.get("PYTEST_CURRENT_TEST", "")[:300])
            except Exception:  # noqa: BLE001 - never change the launch
                pass

        sys.addaudithook(_audit)
        _note("start", base_interpreter=sys.prefix == sys.base_prefix)
        atexit.register(lambda: _note(
            "end", is_pytest="pytest" in sys.modules, trusted_paths_imported=_TARGET in sys.modules,
            real_adapter_calls=_calls[0], script=os.path.basename(sys.argv[0]) if sys.argv and sys.argv[0] not in ("-c", "-m") else (sys.argv[0] if sys.argv else ""),
        ))
    except Exception:  # noqa: BLE001 - an observer must never change the observed process
        pass
