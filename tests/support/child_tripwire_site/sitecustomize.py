"""Loads the child tripwire in a child whose program cannot carry the prelude line.

Test support only. A test that launches a script file or a module puts this folder on the
child's PYTHONPATH through `child_tripwire.hooked_environment`. Python then imports this module
at start-up, before the child's own program, and the tripwire installs itself. Without the record
variable it does nothing. If it cannot load, the parent's check fails: no load was recorded.
"""

import os

if os.environ.get("OPTIMUS_TEST_CHILD_TRIPWIRE_FILE"):
    import sys

    import tests.support.child_tripwire as _child_tripwire

    try:
        _child_tripwire.install()
    except RuntimeError as error:
        if str(error) != _child_tripwire.KEYRING_REFUSAL:
            raise
        # site.py reports an exception from sitecustomize and carries on into the child's program; this refusal must
        # stop the interpreter before that program runs (#540, Codex round 2).
        print(error, file=sys.stderr, flush=True)
        os._exit(3)
