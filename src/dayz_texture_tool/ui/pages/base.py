"""页面外壳：标题 + 工具条 + 主体 + 底部状态栏。

所有页面都长这样，只是工具条里的控件和主体不同。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .. import theme
from ..theme import PAGE_PAD
from ..widgets.status_bar import StatusBar


class BasePage(QWidget):
    def __init__(self, title: str, action_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Page")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PageTitle")
        root.addWidget(self.title_label)

        self.toolbar = QWidget()
        self.toolbar.setObjectName("Toolbar")
        self.toolbar_layout = QHBoxLayout(self.toolbar)
        self.toolbar_layout.setContentsMargins(PAGE_PAD, 0, PAGE_PAD, 12)
        self.toolbar_layout.setSpacing(10)
        root.addWidget(self.toolbar)

        self._body = QWidget()
        self._body.setObjectName("Body")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(0)
        root.addWidget(self._body, 1)

        self.status = StatusBar(action_text)
        root.addWidget(self.status)

    # ---------------------------------------------------------------- 装配
    def add_toolbar(self, *widgets: QWidget) -> None:
        for widget in widgets:
            self.toolbar_layout.addWidget(widget, 0, Qt.AlignVCenter)

    def add_toolbar_stretch(self) -> None:
        self.toolbar_layout.addStretch(1)

    def set_body(self, widget: QWidget) -> None:
        self._body_layout.addWidget(widget, 1)

    def add_footer(self, widget: QWidget) -> None:
        """夹在主体和状态栏之间（问题面板用）。"""
        layout = self.layout()
        layout.insertWidget(layout.count() - 1, widget)

    # ---------------------------------------------------------------- 语言
    def retranslate(self) -> None:
        """切语言时重设文案。子类覆盖。"""
