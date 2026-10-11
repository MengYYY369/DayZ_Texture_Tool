"""图标。全部来自 qtawesome（MIT，自带上万图标），一个都不自己画。

图标名集中在这里 —— 以后想换图标只改这一处。
"""

from __future__ import annotations

import qtawesome as qta
from PySide6.QtGui import QIcon, QPixmap

# 侧边栏与界面里用到的图标
ICON_NAMES = {
    # 侧边栏
    "game": "ph.squares-four",  # 四格拆分
    "pbr": "ph.stack-simple",  # 一叠贴图成组
    "mark": "ph.drop",  # 水印
    "smdi": "ph.sun-dim",  # 高光强度
    "rvmat": "ph.swatches",  # 材质变体
    "gear": "ph.gear-six",  # 设置
    "lang": "ph.translate",  # 语言
    # 工具条
    "add": "ph.plus",
    "caret_down": "ph.caret-down",
    "caret_left": "ph.caret-left",
    "caret_right": "ph.caret-right",
    "caret_up": "ph.caret-up",
    "folder": "ph.folder-open",
    "file": "ph.image",
    # 开关
    "dot_on": "ph.circle-fill",
    "dot_off": "ph.circle",
    # 状态
    "close": "ph.x",
    "check": "ph.check",
    "warn": "ph.warning",
    "drop_hint": "ph.file-arrow-down",
    "zoom": "ph.arrows-out",
}

ICON_SIZE = 18


def icon(kind: str, color: str, disabled: str | None = None) -> QIcon:
    return qta.icon(
        ICON_NAMES[kind],
        color=color,
        color_disabled=disabled or color,
    )


def pixmap(kind: str, color: str, size: int = ICON_SIZE) -> QPixmap:
    return qta.icon(ICON_NAMES[kind], color=color).pixmap(size, size)
