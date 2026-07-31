"""Artifact size and structural bounds for evidence redaction handlers."""

from __future__ import annotations

# Frozen by the redaction-gate implementation plan unless amended.
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024
MAX_JSON_DEPTH = 64
MAX_DECODED_STRING_BYTES = 1024 * 1024
MAX_COLLECTION_MEMBERS = 100_000
MAX_NDJSON_TAIL_BYTES = 1024 * 1024
STREAM_READ_BYTES = 64 * 1024

# Image bounds (Task 6).
MAX_IMAGE_BYTES = 32 * 1024 * 1024
MAX_IMAGE_AXIS_PIXELS = 10_000
MAX_IMAGE_DECODED_PIXELS = 40_000_000
