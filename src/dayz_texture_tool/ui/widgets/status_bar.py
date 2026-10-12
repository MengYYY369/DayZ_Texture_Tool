"""底部状态栏：左边一句话，右边百分比 + 进度条 + 主操作按钮。"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from .. import theme
from ..theme import PAGE_PAD, PROGRESS_W, PT_SMALL, STATUS_H
from .toolbar import primary_button


class Progress(QWidget):
    """一条 4px 的进度条。空闲时是空槽。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(PROGRESS_W, 4)
        self._value = 0.0

    def set_value(self, value: float) -> None:
        value = max(0.0, min(1.0, value))
        if abs(value - self._value) < 0.001:
            return
        self._value = value
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t.well))
        p.drawRoundedRect(self.rect(), 2, 2)
        if self._value > 0:
            width = max(4, int(self.width() * self._value))
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRect(0, 0, width, self.height()), 2, 2)
        p.end()


class StatusBar(QWidget):
    action_clicked = Signal()

    def __init__(self, action_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(STATUS_H)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(PAGE_PAD, 0, PAGE_PAD, 0)
        lay.setSpacing(14)

        self._status = QLabel("")
        self._status.setObjectName("SmallDim")
        lay.addWidget(self._status)
        lay.addStretch(1)

        self._pct = QLabel("")
        self._pct.setObjectName("SmallDim")
        self._pct.hide()
        lay.addWidget(self._pct)

        self._progress = Progress()
        lay.addWidget(self._progress)

        self.action = None
        if action_text:
            lay.addSpacing(4)
            self.action = primary_button(action_text)
            self.action.clicked.connect(self.action_clicked.emit)
            lay.addWidget(self.action)

    def set_status(self, text: str) -> None:
        self._status.setText(text)

    def set_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self._progress.set_value(0.0)
            self._pct.hide()
            return
        self._progress.set_value(done / total)
        self._pct.setText(f"{int(done / total * 100)}%")
        self._pct.show()

    def reset_progress(self) -> None:
        self._progress.set_value(0.0)
        self._pct.hide()

    def set_action_enabled(self, enabled: bool) -> None:
        if self.action is not None:
            self.action.setEnabled(enabled)

    def set_action_text(self, text: str) -> None:
        if self.action is not None:
            self.action.setText(text)
