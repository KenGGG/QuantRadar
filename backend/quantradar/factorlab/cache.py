from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def operator_bundle_hash() -> str:
    root = Path(__file__).parents[1] / "datahub" / "alpha101"
    digest = hashlib.sha256()
    for name in ("operators.py", "expressions.py", "catalog.py"):
        digest.update((root / name).read_bytes())
    return digest.hexdigest()


def cache_key(value: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
