"""底部的问题面板：失败和跳过分开列，一眼看出这次配置对不对。"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import theme
from ..icons import pixmap

NAME_W = 180


class IssueRow(QWidget):
    def __init__(self, name: str, reason: str, failed: bool, parent=None) -> None:
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        mark = QLabel(self)
        mark.setFixedSize(16, 16)
        t = theme.current()
        mark.setPixmap(pixmap("warn" if failed else "dot_off", t.err if failed else t.skip, 13))
        lay.addWidget(mark)

        title = QLabel(name, self)
        title.setObjectName("TinyErr" if failed else "TinyMuted")
        title.setFixedWidth(NAME_W)
        lay.addWidget(title)

        text = QLabel(reason, self)
        text.setObjectName("TinyMuted")
        text.setWordWrap(False)
        lay.addWidget(text, 1)


class IssuesPanel(QWidget):
    """平时藏着，有问题才冒出来。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Issues")
        self._collapsed = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 8, 22, 8)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(self)
        self.title.setObjectName("SectionTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.toggle = QPushButton(self)
        self.toggle.setObjectName("IssuesToggle")
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.clicked.connect(self._flip)
        head.addWidget(self.toggle)
        lay.addLayout(head)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setMaximumHeight(118)
        self._inner = QWidget(self._scroll)
        self._inner.setObjectName("Inner")
        self._body = QVBoxLayout(self._inner)
        self._body.setContentsMargins(0, 0, 0, 0)
        self._body.setSpacing(2)
        self._scroll.setWidget(self._inner)
        lay.addWidget(self._scroll)

        self.hide()

    # ------------------------------------------------------------ 内容

    def set_issues(self, failed: list[tuple[str, str]], skipped: list[tuple[str, str]]) -> None:
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()

        total = len(failed) + len(skipped)
        self.setVisible(total > 0)
        if not total:
            return

        self.title.setText(self.tr("Issues · {count}").format(count=total))
        self._add_group(self.tr("Failed · {count}").format(count=len(failed)), failed, True)
        self._add_group(self.tr("Skipped · {count}").format(count=len(skipped)), skipped, False)
        self._body.addStretch(1)
        self._refresh_toggle()

    def _add_group(self, label: str, rows: list[tuple[str, str]], failed: bool) -> None:
        if not rows:
            return
        head = QLabel(label, self._inner)
        head.setObjectName("TinyErr" if failed else "TinyMuted")
        head.setContentsMargins(0, 4, 0, 2)
        self._body.addWidget(head)
        for name, reason in rows:
            self._body.addWidget(IssueRow(name, reason, failed, self._inner))

    def _flip(self) -> None:
        self._collapsed = not self._collapsed
        self._scroll.setVisible(not self._collapsed)
        self._refresh_toggle()

    def _refresh_toggle(self) -> None:
        self.toggle.setText(self.tr("Show ▾") if self._collapsed else self.tr("Hide ▴"))

    def retranslate(self) -> None:
        self._refresh_toggle()


__all__ = ["IssuesPanel"]
