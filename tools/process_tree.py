"""`tools.process_tree` is `optimus.runtime.process_tree`, where the containment code moved (Plan 12.3).

The tools and the test harness keep importing it by this name. The module itself is the alias, so a
patch through either name reaches the same functions and the same job registry.
"""

import sys

from optimus.runtime import process_tree

sys.modules[__name__] = process_tree
