import json
import os
from pathlib import Path
from typing import Tuple, Union

from bullet_trade.core.globals import log

DEFAULT_CONFIG_DIR = ".bullet-trade"
DEFAULT_SETTINGS_FILE = "setting.json"
DEFAULT_ROOT_DIR = "bullet-trade"


def _base_home() -> Path:
    override = os.environ.get("BULLET_TRADE_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home()


def _settings_path(base_home: Path) -> Path:
    return base_home / DEFAULT_CONFIG_DIR / DEFAULT_SETTINGS_FILE


def _load_root_dir(base_home: Path) -> Tuple[Path, Path, bool]:
    settings_path = _settings_path(base_home)
    default_root = base_home / DEFAULT_ROOT_DIR
    data = {}
    if settings_path.exists():
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    raw_root = data.get("root_dir", default_root)
    try:
        root_dir = Path(raw_root).expanduser()
    except TypeError:
        root_dir = default_root
    return root_dir, settings_path, settings_path.exists()


def _is_subpath(base: Path, target: Path) -> bool:
    try:
        base_resolved = base.resolve()
        target_resolved = target.resolve()
    except Exception:
        return False
    try:
        target_resolved.relative_to(base_resolved)
        return True
    except ValueError:
        return False


def _ensure_initialized(root_dir: Path, settings_path: Path, settings_exists: bool) -> None:
    if root_dir.exists():
        return
    # 只有根目录缺失时认为未初始化；同时提示设置文件位置
    msg = (
        f"研究环境未初始化，请运行 bullet-trade lab 初始化研究环境。"
        f" 预期根目录: {root_dir}，设置文件: {settings_path}"
    )
    log.warning(msg)
    raise FileNotFoundError(msg)


def _normalize_and_validate(path: str) -> Tuple[str, Path, Path]:
    if not isinstance(path, str):
        raise TypeError("path 必须是字符串")
    relative = path.strip()
    if not relative:
        raise ValueError("path 不能为空")
    if os.path.isabs(relative):
        raise ValueError(f"path 必须是研究根目录下的相对路径: {relative}")

    base_home = _base_home()
    root_dir, settings_path, settings_exists = _load_root_dir(base_home)
    _ensure_initialized(root_dir, settings_path, settings_exists)

    absolute = (root_dir / relative).resolve()
    root_resolved = root_dir.resolve()
    if not _is_subpath(root_resolved, absolute):
        raise ValueError(
            f"路径越界，仅允许读写研究根目录下的文件。相对路径: {relative}，绝对路径: {absolute}"
        )
    return relative, absolute, root_resolved


def read_file(path: str) -> bytes:
    """
    在回测/模拟/实盘中读取研究目录文件，返回原始字节内容。
    """
    relative, absolute, _ = _normalize_and_validate(path)
    log.info(f"read_file 相对路径: {relative} 绝对路径: {absolute}")
    try:
        return absolute.read_bytes()
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"文件不存在。相对路径: {relative}，绝对路径: {absolute}"
        ) from exc


def write_file(path: str, content: Union[str, bytes, bytearray, memoryview], append: bool = False) -> None:
    """
    在回测/模拟/实盘中写入研究目录文件。字符串以 UTF-8 编码。
    """
    relative, absolute, _ = _normalize_and_validate(path)
    log.info(f"write_file 相对路径: {relative} 绝对路径: {absolute}")

    if isinstance(content, str):
        data = content.encode("utf-8")
    elif isinstance(content, (bytes, bytearray, memoryview)):
        data = bytes(content)
    else:
        raise TypeError("content 仅支持 str/bytes/bytearray/memoryview")

    absolute.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if append else "wb"
    with open(absolute, mode) as f:
        f.write(data)
    return None


__all__ = ["read_file", "write_file"]
