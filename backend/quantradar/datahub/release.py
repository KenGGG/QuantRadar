"""Immutable paired-Dolt release manifests and atomic current pointer."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ReleaseStore:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.releases = self.root / "releases"
        self.current_path = self.root / "current.json"

    @staticmethod
    def _canonical(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    def publish(
        self, *, base_commit: str, supplemental_commit: str, datasets: dict[str, Any], source_adapters: dict[str, str], schema_version: str = "datahub-v1", metadata: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        if not base_commit:
            raise ValueError("base_commit is required")
        if not supplemental_commit:
            raise ValueError("supplemental_commit is required")
        identity = {
            "base_commit": base_commit,
            "supplemental_commit": supplemental_commit,
            "schema_version": schema_version,
            "datasets": datasets,
            "source_adapters": source_adapters,
            "metadata": metadata or {},
        }
        release_id = "R" + hashlib.sha256(self._canonical(identity)).hexdigest()[:16]
        manifest = {**identity, "release_id": release_id, "published_at": datetime.now(timezone.utc).isoformat()}
        self.releases.mkdir(parents=True, exist_ok=True)
        manifest_path = self.releases / f"{release_id}.json"
        if manifest_path.exists():
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
            if {key: existing[key] for key in identity} != identity:
                raise ValueError(f"release identity collision: {release_id}")
            manifest = existing
        else:
            self._atomic_json(manifest_path, manifest)
        self._atomic_json(self.current_path, manifest)
        return manifest

    def current(self) -> dict[str, Any]:
        if not self.current_path.is_file():
            raise FileNotFoundError("no DataHub release has been published")
        return json.loads(self.current_path.read_text(encoding="utf-8"))

    def resolve(self, release_id: str | None = None) -> dict[str, Any]:
        if release_id is None:
            return self.current()
        path = self.releases / f"{release_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"DataHub release not found: {release_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _atomic_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("wb") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
