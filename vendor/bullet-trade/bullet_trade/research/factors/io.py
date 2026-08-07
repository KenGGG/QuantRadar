import json
import os
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

import pandas as pd

from bullet_trade.core.globals import log
from bullet_trade.research.io import _base_home, _load_root_dir  # type: ignore


def _default_output_dir(output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser()
    base_home = _base_home()
    root_dir, _settings_path, _exists = _load_root_dir(base_home)
    fallback = root_dir / "results"
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback
    except Exception:
        cwd_fallback = Path.cwd() / "results"
        cwd_fallback.mkdir(parents=True, exist_ok=True)
        return cwd_fallback


def _save_df(df: pd.DataFrame, path: Path, fmt: str) -> None:
    if fmt == "csv":
        df.to_csv(path, index=False)
    elif fmt == "parquet":
        try:
            df.to_parquet(path, index=False)
        except Exception as exc:
            raise RuntimeError("写入 Parquet 失败，请确认安装了 pyarrow/fastparquet") from exc
    elif fmt == "pickle":
        df.to_pickle(path)
    elif fmt == "sqlite":
        import sqlite3

        conn = sqlite3.connect(path)
        try:
            df.to_sql("data", conn, if_exists="replace", index=False)
        finally:
            conn.close()
    else:
        raise ValueError(f"不支持的格式: {fmt}")


def save_results(
    result: Any,
    output_dir: Optional[str] = None,
    name: str = "factor_result",
    formats: Tuple[str, ...] = ("csv",),
) -> Dict[str, Path]:
    """
    保存因子管线/评估结果，支持多格式。
    """
    output_root = _default_output_dir(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    data_map: Dict[str, pd.DataFrame] = {}
    meta: Dict[str, Any] = {}

    if hasattr(result, "data"):
        data_map["data"] = getattr(result, "data")
    if hasattr(result, "bucket_returns"):
        data_map["bucket_returns"] = getattr(result, "bucket_returns")
    if hasattr(result, "portfolio_returns"):
        data_map["portfolio_returns"] = getattr(result, "portfolio_returns")
    if hasattr(result, "ic"):
        data_map["ic"] = getattr(result, "ic").reset_index().rename(columns={"index": "date", 0: "ic"})
    if hasattr(result, "rank_ic"):
        data_map["rank_ic"] = getattr(result, "rank_ic").reset_index().rename(
            columns={"index": "date", 0: "rank_ic"}
        )
    if hasattr(result, "metrics"):
        meta["metrics"] = getattr(result, "metrics")
    if hasattr(result, "meta"):
        meta.update(getattr(result, "meta") or {})
    if hasattr(result, "filter_counts"):
        meta["filter_counts"] = getattr(result, "filter_counts")

    saved: Dict[str, Path] = {}
    for df_name, df in data_map.items():
        for fmt in formats:
            suffix = "db" if fmt == "sqlite" else fmt
            path = output_root / f"{name}_{df_name}.{suffix}"
            _save_df(df, path, fmt)
            saved[f"{df_name}.{fmt}"] = path
            log.info("结果已保存 %s -> %s", df_name, path)

    if meta:
        meta_path = output_root / f"{name}_meta.json"
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        saved["meta.json"] = meta_path
        log.info("元数据已保存 -> %s", meta_path)

    return saved


def load_results(path: str) -> Dict[str, Any]:
    """
    加载保存的结果（自动识别 CSV/Parquet/Pickle/SQLite）。
    """
    p = Path(path).expanduser()
    if p.is_dir():
        files = {f.suffix.replace(".", ""): f for f in p.iterdir() if f.is_file()}
        data: Dict[str, Any] = {}
        for suffix, file in files.items():
            if suffix in {"csv", "parquet", "pickle"} and file.name.startswith("factor_result_data"):
                if suffix == "csv":
                    data["data"] = pd.read_csv(file)
                elif suffix == "parquet":
                    data["data"] = pd.read_parquet(file)
                else:
                    data["data"] = pd.read_pickle(file)
            if suffix == "json" and "meta" in file.name:
                data["meta"] = json.loads(file.read_text(encoding="utf-8"))
        return data
    else:
        # 单文件加载
        suffix = p.suffix.lower()
        if suffix == ".csv":
            return {"data": pd.read_csv(p)}
        if suffix == ".parquet":
            return {"data": pd.read_parquet(p)}
        if suffix == ".pkl" or suffix == ".pickle":
            return {"data": pd.read_pickle(p)}
    raise FileNotFoundError(f"无法识别的路径或文件: {path}")


__all__ = ["save_results", "load_results"]
