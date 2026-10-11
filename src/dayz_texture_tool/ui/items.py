"""列表里的数据模型。

一行 = 一次执行。比如 Game2PBR 是「1 张原图 → N 张输出」，PBR2DayZ 是
「5 张一组 → 最多 4 张输出」，水印是「1 张原图 → 一句结果」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

PENDING = "pending"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
SKIPPED = "skipped"


@dataclass
class Slot:
    """一格小图。path 为 None 表示这一格这次没有东西（灰底槽）。"""

    label: str
    path: Path | None = None
    size_text: str = ""
    missing: bool = False
    placeholder: str = ""  # 读不出缩略图时格子里的大字。空着就显示文件扩展名。


@dataclass
class Item:
    key: str
    title: str
    subtitle: str = ""
    inputs: list[Slot] = field(default_factory=list)
    outputs: list[Slot] = field(default_factory=list)
    output_note: str = ""
    size_top: str = ""
    size_bottom: str = ""
    status: str = PENDING
    status_note: str = ""
    checked: bool = True
    selectable: bool = True
