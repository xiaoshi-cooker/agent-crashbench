"""Canonical JSON serialization and content addressing.

Every digest in this repo goes through :func:`canonical_json` so that two
semantically equal payloads always produce the same hash regardless of dict
insertion order or platform.

Timestamps across the repo are integer microseconds since the Unix epoch
(UTC). Comparisons are plain integer comparisons; no floats, no ISO parsing
on hot paths.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any

__all__ = ["canonical_json", "sha256_hex", "digest", "now_us"]


def canonical_json(obj: Any) -> str:
    """Serialize *obj* to a canonical JSON string.

    Sorted keys, compact separators, UTF-8 preserved, NaN/Infinity rejected.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_hex(data: str | bytes) -> str:
    """SHA-256 hex digest of *data* (str is encoded as UTF-8)."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def digest(obj: Any) -> str:
    """Content address of *obj*: sha256 over its canonical JSON form."""
    return sha256_hex(canonical_json(obj))


def now_us() -> int:
    """Current UTC time as integer microseconds since the Unix epoch."""
    return time.time_ns() // 1_000
