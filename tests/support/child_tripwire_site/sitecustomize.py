"""Loads the child tripwire in a child whose program cannot carry the prelude line.

Test support only. A test that launches a script file or a module puts this folder on the
child's PYTHONPATH through `child_tripwire.hooked_environment`. Python then imports this module
at start-up, before the child's own program, and the tripwire installs itself. Without the record
variable it does nothing. If it cannot load, the parent's check fails: no load was recorded.
"""

import os

if os.environ.get("OPTIMUS_TEST_CHILD_TRIPWIRE_FILE"):
    import tests.support.child_tripwire as _child_tripwire

    _child_tripwire.install()
