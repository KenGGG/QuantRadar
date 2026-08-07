"""PostgreSQL 持久化层（Closing Phase 2：PERSIST_WORKER_PASS）。

提供 5 张表与 CRUD：
    - Strategy        策略（源码 + 策略哈希）
    - BacktestRun     回测运行（配置 / 状态 / 结果快照 / 指标 / 结果哈希）
    - Experiment      实验（复用 Phase 9 语义，落库版）
    - Snapshot        快照 manifest（按 snapshot_id 唯一）
    - Metrics         指标（按 run_id 唯一）

连接串来自环境变量 QUANT_RADAR_PG_URL（如 postgresql+psycopg2://user:pass@host:5432/db）。
未设置时 get_engine() 抛 RuntimeError；测试据此 skip。绝不在代码/提交中硬编码凭证。
建表通过 init_db()（SQLAlchemy create_all，幂等）；本文件不发出任何 DROP。
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()


def _now() -> datetime.datetime:
    return datetime.datetime.now()


def _pg_url() -> Optional[str]:
    return os.environ.get("QUANT_RADAR_PG_URL")


_engine = None
_sessionmaker = None


def get_engine():
    """返回（惰性创建）SQLAlchemy engine；未配置 QUANT_RADAR_PG_URL 抛 RuntimeError。"""
    global _engine
    url = _pg_url()
    if not url:
        raise RuntimeError("QUANT_RADAR_PG_URL 未设置：无法连接 PostgreSQL")
    if _engine is None:
        _engine = create_engine(url, future=True, pool_pre_ping=True)
    return _engine


def get_session():
    """返回绑定当前 engine 的 Session。"""
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _sessionmaker()


def init_db() -> None:
    """幂等建表（不 DROP）。"""
    Base.metadata.create_all(get_engine())


def drop_all() -> None:
    """仅测试用：清空全部表。"""
    Base.metadata.drop_all(get_engine())


# ----------------------------- 模型 -----------------------------


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    source = Column(Text, nullable=False)
    strategy_hash = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "strategy_hash": self.strategy_hash,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    run_id = Column(String(64), primary_key=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=True)
    config = Column(JSON, nullable=True)
    status = Column(String(16), nullable=False, default="PENDING", index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    result_hash = Column(String(64), nullable=True, index=True)
    snapshot = Column(JSON, nullable=True)
    metrics = Column(JSON, nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "strategy_id": self.strategy_id,
            "config": self.config,
            "status": self.status,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result_hash": self.result_hash,
            "snapshot": self.snapshot,
            "metrics": self.metrics,
        }


class Experiment(Base):
    __tablename__ = "experiments"
    __table_args__ = (UniqueConstraint("name", name="uq_experiment_name"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    kind = Column(String(32), nullable=False, default="backtest")
    config = Column(JSON, nullable=True)
    result_fingerprint = Column(String(64), nullable=True, index=True)
    metrics = Column(JSON, nullable=True)
    snapshot = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "config": self.config,
            "result_fingerprint": self.result_fingerprint,
            "metrics": self.metrics,
            "snapshot": self.snapshot,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Snapshot(Base):
    __tablename__ = "snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_id = Column(String(64), nullable=False, unique=True, index=True)
    run_id = Column(String(64), ForeignKey("backtest_runs.run_id"), nullable=True)
    result_hash = Column(String(64), nullable=True, index=True)
    payload = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "snapshot_id": self.snapshot_id,
            "run_id": self.run_id,
            "result_hash": self.result_hash,
            "payload": self.payload,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Metrics(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), ForeignKey("backtest_runs.run_id"), nullable=False, unique=True)
    metrics = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=_now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "run_id": self.run_id,
            "metrics": self.metrics,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ----------------------------- CRUD -----------------------------


def save_strategy(name: str, source: str, strategy_hash: str, session=None) -> Strategy:
    own = session is None
    s = session or get_session()
    try:
        obj = Strategy(name=name, source=source, strategy_hash=strategy_hash)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj
    finally:
        if own:
            s.close()


def create_run(run_id: str, config: Dict[str, Any], strategy_id: Optional[int] = None,
              session=None) -> BacktestRun:
    own = session is None
    s = session or get_session()
    try:
        obj = BacktestRun(run_id=run_id, config=config, strategy_id=strategy_id, status="PENDING")
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj
    finally:
        if own:
            s.close()


def update_run(run_id: str, session=None, **fields) -> Optional[BacktestRun]:
    own = session is None
    s = session or get_session()
    try:
        obj = s.get(BacktestRun, run_id)
        if obj is None:
            return None
        for k, v in fields.items():
            setattr(obj, k, v)
        s.commit()
        s.refresh(obj)
        return obj
    finally:
        if own:
            s.close()


def get_run(run_id: str, session=None) -> Optional[Dict[str, Any]]:
    own = session is None
    s = session or get_session()
    try:
        obj = s.get(BacktestRun, run_id)
        return obj.to_dict() if obj else None
    finally:
        if own:
            s.close()


def list_runs(limit: int = 50, session=None) -> List[Dict[str, Any]]:
    """列出近期运行（按创建时间倒序）。"""
    own = session is None
    s = session or get_session()
    try:
        rows = (
            s.query(BacktestRun)
            .order_by(BacktestRun.created_at.desc())
            .limit(limit)
            .all()
        )
        return [r.to_dict() for r in rows]
    finally:
        if own:
            s.close()


def save_snapshot_record(snapshot_id: str, run_id: Optional[str], payload: Dict[str, Any],
                         result_hash: str, session=None) -> Snapshot:
    own = session is None
    s = session or get_session()
    try:
        obj = Snapshot(snapshot_id=snapshot_id, run_id=run_id,
                       result_hash=result_hash, payload=payload)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj
    finally:
        if own:
            s.close()


def save_metrics(run_id: str, metrics: Dict[str, Any], session=None) -> Metrics:
    own = session is None
    s = session or get_session()
    try:
        obj = Metrics(run_id=run_id, metrics=metrics)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj
    finally:
        if own:
            s.close()


def save_experiment(name: str, kind: str, config: Dict[str, Any], result_fingerprint: str,
                    metrics: Dict[str, Any], snapshot: Optional[Dict[str, Any]], session=None) -> Experiment:
    own = session is None
    s = session or get_session()
    try:
        obj = Experiment(name=name, kind=kind, config=config,
                         result_fingerprint=result_fingerprint, metrics=metrics, snapshot=snapshot)
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj
    finally:
        if own:
            s.close()


def get_experiment(name: str, session=None) -> Optional[Dict[str, Any]]:
    own = session is None
    s = session or get_session()
    try:
        obj = s.query(Experiment).filter(Experiment.name == name).first()
        return obj.to_dict() if obj else None
    finally:
        if own:
            s.close()


def list_experiments(session=None) -> List[str]:
    own = session is None
    s = session or get_session()
    try:
        return [r[0] for r in s.query(Experiment.name).order_by(Experiment.created_at).all()]
    finally:
        if own:
            s.close()


__all__ = [
    "Base", "Strategy", "BacktestRun", "Experiment", "Snapshot", "Metrics",
    "get_engine", "get_session", "init_db", "drop_all",
    "save_strategy", "create_run", "update_run", "get_run", "list_runs",
    "save_snapshot_record", "save_metrics", "save_experiment", "get_experiment", "list_experiments",
]
