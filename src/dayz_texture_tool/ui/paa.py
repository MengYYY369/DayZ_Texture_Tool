"""PAA 预览：Qt 的图片读取器不认 .paa，得先让 ImageToPAA.exe 解成 PNG。

解出来的 PNG 放在一个进程级临时目录里，同一个文件只解一次 —— 列表里的缩略图和
点开的大图共用同一份结果。临时目录在退出时删掉。
"""

from __future__ import annotations

import atexit
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

_LOCK = threading.Lock()
_CACHE: dict[str, Path | None] = {}
_TEMP: Path | None = None
_SEQ = 0
_TOOL = ""


def set_tool(path: str | Path | None) -> None:
    """ImageToPAA.exe 在哪。启动时和设置页改路径时各调一次。"""
    global _TOOL
    _TOOL = str(path or "")


def readable(path: Path) -> Path | None:
    """给一个路径，返回能读的那一个。

    不是 .paa 就原样返回；是 .paa 就解成 PNG。解不出来（没配工具、工具报错）返回 None。
    """
    if path.suffix.lower() != ".paa":
        return path
    key = str(path)
    with _LOCK:
        if key in _CACHE:
            return _CACHE[key]
    decoded = _decode(path)
    with _LOCK:
        _CACHE[key] = decoded
    return decoded


def _temp_dir() -> Path:
    global _TEMP
    if _TEMP is None:
        _TEMP = Path(tempfile.mkdtemp(prefix="dayz_preview_"))
        atexit.register(shutil.rmtree, _TEMP, True)
    return _TEMP


def _decode(path: Path) -> Path | None:
    global _SEQ
    tool = Path(_TOOL) if _TOOL else None
    if tool is None or not tool.exists():
        return None
    with _LOCK:
        _SEQ += 1
        target = _temp_dir() / f"paa_{_SEQ}.png"
    kwargs: dict = {"capture_output": True, "text": True, "check": False}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        completed = subprocess.run([str(tool), str(path), str(target)], **kwargs)
    except OSError:
        return None
    if completed.returncode != 0 or not target.exists():
        return None
    return target
