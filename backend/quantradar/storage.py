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

测试隔离（安全边界）：
  - 测试应使用专用测试库，连接串来自 QUANT_RADAR_TEST_PG_URL（库名须含 `_test`）。
  - get_engine() 在 QUANT_RADAR_TEST_PG_URL 已设置时优先用它，使全部 CRUD 指向测试库，
    从而与正式库（QUANT_RADAR_PG_URL）物理隔离。
  - drop_all() 对任何「库名不含 `_test`」的连接串一律拒绝执行，杜绝误 DROP 正式库。
    （这是必须停止条件：不可逆/未授权 DB 写。即使测试代码出错也不会波及正式库。）
"""

from __future__ import annotations

import datetime
import os
from typing import Any, Dict, List, Optional, Union

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
    """返回当前生效的连接串。

    测试隔离：若设置了 QUANT_RADAR_TEST_PG_URL 则优先使用（指向专用 `_test` 库），
    使全部 CRUD 落到测试库，与正式库物理隔离。运行时只设置 QUANT_RADAR_PG_URL，故不受影响。
    """
    return os.environ.get("QUANT_RADAR_TEST_PG_URL") or os.environ.get("QUANT_RADAR_PG_URL")


def _db_name(url: Optional[str]) -> Optional[str]:
    """从连接串解析数据库名（postgresql+psycopg2://user:pass@host:port/db）。"""
    if not url:
        return None
    # 去掉 query/fragment
    path = url.split("?")[0].split("#")[0]
    # 取最后一个 '/'
    last = path.rfind("/")
    if last == -1:
        return None
    return path[last + 1 :] or None


_engine = None
_sessionmaker = None


def get_engine():
    """返回（惰性创建）SQLAlchemy engine；未配置连接串抛 RuntimeError。"""
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
    """仅测试用：清空全部表。

    安全边界：任何「库名不含 '_test'」的连接串一律拒绝执行，杜绝误 DROP 正式库
    （不可逆/未授权 DB 写为必须停止条件）。测试应连接 QUANT_RADAR_TEST_PG_URL 指向的 `_test` 库。
    """
    url = _pg_url()
    name = _db_name(url)
    if not name or "_test" not in name:
        raise RuntimeError(
            f"拒绝执行 drop_all：数据库名 {name!r} 不含 '_test'。"
            f"测试必须连接专用测试库（QUANT_RADAR_TEST_PG_URL，库名含 '_test'），禁止对正式库 DROP。"
        )
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


def get_strategy(strategy_id: int, session=None) -> Optional[Strategy]:
    """按 id 取策略记录（含源码）；不存在返回 None。"""
    own = session is None
    s = session or get_session()
    try:
        obj = s.get(Strategy, strategy_id)
        return obj
    finally:
        if own:
            s.close()


def list_runs_by_status(status: Union[str, List[str]], limit: int = 200, session=None) -> List[Dict[str, Any]]:
    """列出某状态（或状态列表）的最近运行（按创建时间倒序），用于重启恢复。

    接受单个状态字符串或状态列表（如 ["RUNNING", "PENDING"]），用于把进程异常退出时
    遗留在内存队列中、未真正完成的任务（RUNNING 中途中断 + PENDING 尚未出队）全部找回。
    """
    own = session is None
    s = session or get_session()
    try:
        q = s.query(BacktestRun).order_by(BacktestRun.created_at.desc())
        if isinstance(status, (list, tuple, set)):
            q = q.filter(BacktestRun.status.in_(status))
        else:
            q = q.filter(BacktestRun.status == status)
        rows = q.limit(limit).all()
        return [r.to_dict() for r in rows]
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
    "save_strategy", "create_run", "update_run", "get_run", "get_strategy",
    "list_runs", "list_runs_by_status",
    "save_snapshot_record", "save_metrics", "save_experiment", "get_experiment", "list_experiments",
]
