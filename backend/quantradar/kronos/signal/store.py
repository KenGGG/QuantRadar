from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
import pandas as pd

from .manifest import content_hash, file_hash, write_json_atomic


class ArtifactIntegrityError(RuntimeError):
    """A persisted SignalRun does not match its immutable fingerprint or hashes."""


class SignalArtifactStore:
    def __init__(
        self,
        run_dir: Path,
        *,
        fingerprint: Mapping[str, Any],
    ) -> None:
        self.run_dir = run_dir
        self.fingerprint = dict(fingerprint)
        self.run_id = run_dir.name

    @staticmethod
    def _fingerprint(
        *,
        config: Mapping[str, Any],
        model_lock: Mapping[str, Any],
        data_contract: Mapping[str, Any],
        data_commit: str,
        requested_dates: Iterable[str],
    ) -> dict[str, Any]:
        return {
            "config": dict(config),
            "model_lock": dict(model_lock),
            "data_contract": dict(data_contract),
            "data_commit": data_commit,
            "requested_dates": sorted(str(value) for value in requested_dates),
        }

    @classmethod
    def create(
        cls,
        root: str | Path,
        *,
        config: Mapping[str, Any],
        model_lock: Mapping[str, Any],
        data_contract: Mapping[str, Any],
        data_commit: str,
        requested_dates: Iterable[str],
    ) -> "SignalArtifactStore":
        fingerprint = cls._fingerprint(
            config=config,
            model_lock=model_lock,
            data_contract=data_contract,
            data_commit=data_commit,
            requested_dates=requested_dates,
        )
        run_id = "signal_" + content_hash(fingerprint)[:20]
        run_dir = Path(root) / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "weeks").mkdir(exist_ok=True)
        write_json_atomic(run_dir / "config.json", config)
        write_json_atomic(run_dir / "model_lock.json", model_lock)
        write_json_atomic(run_dir / "data_contract.json", data_contract)
        write_json_atomic(run_dir / "run_fingerprint.json", fingerprint)
        return cls(run_dir, fingerprint=fingerprint)

    @classmethod
    def resume(
        cls,
        run_dir: str | Path,
        *,
        config: Mapping[str, Any],
        model_lock: Mapping[str, Any],
        data_contract: Mapping[str, Any],
        data_commit: str,
        requested_dates: Iterable[str],
    ) -> "SignalArtifactStore":
        target = Path(run_dir)
        expected = cls._fingerprint(
            config=config,
            model_lock=model_lock,
            data_contract=data_contract,
            data_commit=data_commit,
            requested_dates=requested_dates,
        )
        actual = json.loads((target / "run_fingerprint.json").read_text(encoding="utf-8"))
        if content_hash(actual) != content_hash(expected):
            raise ArtifactIntegrityError("run fingerprint does not match requested configuration")
        return cls(target, fingerprint=expected)

    def commit_week(
        self,
        signal_date: str,
        *,
        signals: pd.DataFrame,
        input_manifest: Mapping[str, Any],
        predictions: Mapping[str, np.ndarray],
    ) -> dict[str, Any]:
        day = str(signal_date)
        weeks_dir = self.run_dir / "weeks"
        destination = weeks_dir / day
        if destination.exists():
            return self.validate_week(day)
        stage = Path(tempfile.mkdtemp(prefix=f".{day}.", suffix=".tmp", dir=weeks_dir))
        try:
            write_json_atomic(stage / "input_manifest.json", input_manifest)
            with (stage / "predictions.npz").open("wb") as handle:
                np.savez_compressed(
                    handle,
                    **{name: np.asarray(value) for name, value in predictions.items()},
                )
            signals.to_parquet(stage / "signals.parquet", index=False)
            hashes = {
                name: file_hash(stage / name)
                for name in ("input_manifest.json", "predictions.npz", "signals.parquet")
            }
            manifest = {
                "signal_date": day,
                "input_hash": input_manifest.get("input_content_sha256"),
                "files": hashes,
            }
            write_json_atomic(stage / "partition_manifest.json", manifest)
            os.replace(stage, destination)
            return manifest
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    def validate_week(self, signal_date: str) -> dict[str, Any]:
        week = self.run_dir / "weeks" / str(signal_date)
        manifest_path = week / "partition_manifest.json"
        if not manifest_path.is_file():
            raise ArtifactIntegrityError(f"missing partition manifest for {signal_date}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for name, expected in manifest.get("files", {}).items():
            path = week / name
            if not path.is_file() or file_hash(path) != expected:
                raise ArtifactIntegrityError(f"{name} hash mismatch for {signal_date}")
        return manifest

    def completed_dates(self) -> list[str]:
        dates = []
        for week in sorted((self.run_dir / "weeks").iterdir()):
            if week.is_dir() and not week.name.startswith("."):
                self.validate_week(week.name)
                dates.append(week.name)
        return dates

    def merge(self) -> dict[str, Any]:
        completed = self.completed_dates()
        frames = [
            pd.read_parquet(self.run_dir / "weeks" / day / "signals.parquet")
            for day in completed
        ]
        if not frames:
            raise ArtifactIntegrityError("cannot merge a SignalRun with no completed weeks")
        merged = pd.concat(frames, ignore_index=True)
        sort_columns = [name for name in ("signal_date", "security") if name in merged]
        merged = merged.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)
        temporary = self.run_dir / ".signals.parquet.tmp"
        merged.to_parquet(temporary, index=False)
        os.replace(temporary, self.run_dir / "signals.parquet")
        requested = self.fingerprint["requested_dates"]
        progress = {
            "completed_dates": completed,
            "pending_dates": [day for day in requested if day not in completed],
        }
        write_json_atomic(self.run_dir / "progress.json", progress)
        manifest = {
            "signal_run_id": self.run_id,
            "run_fingerprint_sha256": content_hash(self.fingerprint),
            "signals_sha256": file_hash(self.run_dir / "signals.parquet"),
            "completed_dates": completed,
            "data_commit": self.fingerprint["data_commit"],
            "research_only": True,
            "formal_backtest_ready": False,
            "real_assist_data_ready": False,
        }
        write_json_atomic(self.run_dir / "manifest.json", manifest)
        return manifest
