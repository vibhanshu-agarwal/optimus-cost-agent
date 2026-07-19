"""Neutral shared security package for Optimus diagnostic sanitization.

Plan 9.96, Task 4: optimus_security.sanitization is the only implementation
that converts possibly sensitive runtime data to persistable/exportable
diagnostics. Agent and Gateway wrappers may re-export it but may not fork
its rules (Global Constraint 17).
"""
