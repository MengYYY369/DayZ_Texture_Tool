"""工具条上的控件：下拉、开关、分段、输入框，外加三个按钮。

控件只挂 objectName，颜色全在 theme.py 的全局样式表里 —— 换主题 = 换那一张表。
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QWidget,
)

from .. import icons, theme
from ..theme import CONTROL_H

ICON_PX = 14


def _polish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Combo(QComboBox):
    """下拉选择。items = [(值, 显示文字), ...]

    用 Qt 自带的 QComboBox，不自己画一个。右边的小箭头是从图标库里取的位图，
    不是 Unicode 符号 —— 符号在不同字体下会变成豆腐块。
    """

    changed = Signal(str)

    def __init__(
        self,
        items: list[tuple[str, str]],
        width: int = 190,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Combo")
        self.setFixedHeight(CONTROL_H)
        self.setFixedWidth(width)
        self.setCursor(Qt.PointingHandCursor)
        self._items: list[tuple[str, str]] = []
        self.currentIndexChanged.connect(self._on_index)
        self.set_items(items, notify=False)

    def set_items(self, items: list[tuple[str, str]], notify: bool = False) -> None:
        """换一批选项。选中的那个如果还在新列表里，就继续选着（切语言时要用）。"""
        previous = self.value()
        self._items = list(items)
        index = 0
        for i, (value, _) in enumerate(self._items):
            if value == previous:
                index = i
                break
        blocked = self.blockSignals(True)
        self.clear()
        for value, label in self._items:
            self.addItem(label, value)
        if self._items:
            self.setCurrentIndex(index)
        self.blockSignals(blocked)
        if notify and self._items:
            self.changed.emit(self._items[index][0])

    def set_labels(self, labels: list[str]) -> None:
        """只换显示文字，不动选中的值。"""
        for i, label in enumerate(labels):
            if i < self.count():
                self.setItemText(i, label)

    def _on_index(self, index: int) -> None:
        if 0 <= index < len(self._items):
            self.changed.emit(self._items[index][0])

    def value(self) -> str:
        data = self.currentData()
        return "" if data is None else str(data)

    def set_value(self, value: str, notify: bool = True) -> None:
        for i, (candidate, _) in enumerate(self._items):
            if candidate != value:
                continue
            if i == self.currentIndex():
                return
            if notify:
                self.setCurrentIndex(i)
            else:
                blocked = self.blockSignals(True)
                self.setCurrentIndex(i)
                self.blockSignals(blocked)
            return

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        t = theme.current()
        colour = t.text_muted if not self.isEnabled() else t.text_dim
        pixmap = icons.pixmap("caret_down", colour, ICON_PX)
        ratio = pixmap.devicePixelRatio() or 1.0
        x = self.width() - pixmap.width() / ratio - 10
        y = (self.height() - pixmap.height() / ratio) / 2
        painter = QPainter(self)
        painter.drawPixmap(int(x), int(y), pixmap)


class MenuButton(QPushButton):
    """右边带小箭头的菜单按钮（工具条最右的“＋ 添加”）。

    菜单交给 Qt 自己的 QMenu（setMenu 让 Qt 管弹出位置和键盘操作），箭头跟
    Combo 用同一张位图 —— 不拿 Unicode 符号凑，符号在不同字体下会糊成一团。
    """

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("MenuBtn")
        self.setFixedHeight(CONTROL_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(ICON_PX, ICON_PX))
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.set_label(text)

    def set_label(self, text: str) -> None:
        t = theme.current()
        self.ensurePolished()
        self.setText("  " + text)
        self.setIcon(icons.icon("add", t.text_dim, t.text_muted))
        # 定宽：工具栏会把按钮拉长，不定宽的话文字居中、箭头钉在右边缘，两个就叠上了。
        # 10 左内边距 + 图标 + 文字 + 8 间隙 + 箭头 + 10 右内边距
        self.setFixedWidth(
            10
            + ICON_PX
            + self.fontMetrics().horizontalAdvance(self.text())
            + ICON_PX
            + 30
        )

    def set_items(self, items: list[tuple[str, Callable[[], None]]]) -> None:
        self._menu.clear()
        for label, slot in items:
            self._menu.addAction(label, slot)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        t = theme.current()
        colour = t.text_muted if not self.isEnabled() else t.text_dim
        pixmap = icons.pixmap("caret_down", colour, ICON_PX)
        ratio = pixmap.devicePixelRatio() or 1.0
        x = self.width() - pixmap.width() / ratio - 10
        y = (self.height() - pixmap.height() / ratio) / 2
        painter = QPainter(self)
        painter.drawPixmap(int(x), int(y), pixmap)


class Toggle(QPushButton):
    """开关。勾上时左边的小圆点变亮。"""

    def __init__(
        self, text: str, on: bool = False, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Toggle")
        self.setCheckable(True)
        self.setChecked(on)
        self.setFixedHeight(CONTROL_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(ICON_PX, ICON_PX))
        self._label = text
        self.toggled.connect(self._refresh)
        self._refresh()

    def set_label(self, text: str) -> None:
        self._label = text
        self._refresh()

    def _refresh(self) -> None:
        t = theme.current()
        on = self.isChecked()
        self.setText("  " + self._label)
        self.setIcon(
            icons.icon(
                "dot_on" if on else "dot_off",
                t.accent if on else t.text_muted,
                t.text_muted,
            )
        )
        self.setProperty("on", "true" if on else "false")
        _polish(self)


class Segmented(QWidget):
    """分段切换。options = [(值, 显示文字), ...]"""

    changed = Signal(str)

    def __init__(
        self,
        options: list[tuple[str, str]],
        active: int = 0,
        width: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Seg")
        self.setFixedHeight(CONTROL_H)
        self._min_width = width
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)
        self._buttons: list[tuple[str, QPushButton]] = []
        for i, (value, label) in enumerate(options):
            b = QPushButton(label)
            b.setObjectName("SegBtn")
            b.setFixedHeight(CONTROL_H - 6)
            b.setCursor(Qt.PointingHandCursor)
            b.setCheckable(True)
            b.setChecked(i == active)
            b.clicked.connect(lambda _checked=False, v=value: self.set_value(v))
            lay.addWidget(b)
            self._buttons.append((value, b))
        self._value = options[active][0] if options else ""
        self._fit()

    def _fit(self) -> None:
        """按文字实际宽度定宽 —— 中文四个字比英文两个词宽得多，写死宽度会把字截掉。"""
        needed = 4
        for _, button in self._buttons:
            button.ensurePolished()
            needed += button.sizeHint().width() + 2
        self.setFixedWidth(max(needed, self._min_width))

    def value(self) -> str:
        return self._value

    def set_value(self, value: str, notify: bool = True) -> None:
        if not any(v == value for v, _ in self._buttons):
            return
        changed = value != self._value
        self._value = value
        for v, b in self._buttons:
            b.setChecked(v == value)
        if notify and changed:
            self.changed.emit(value)

    def set_options_enabled(self, enabled: bool) -> None:
        for _, b in self._buttons:
            b.setEnabled(enabled)

    def set_labels(self, labels: list[str]) -> None:
        for (_, button), label in zip(self._buttons, labels):
            button.setText(label)
        self._fit()


class Field(QLineEdit):
    """输入框。"""

    def __init__(
        self, text: str = "", width: int = 120, parent: QWidget | None = None
    ) -> None:
        super().__init__(text, parent)
        self.setObjectName("Field")
        self.setFixedHeight(CONTROL_H - 2)
        self.setFixedWidth(width)

    def set_invalid(self, invalid: bool) -> None:
        self.setProperty("invalid", "true" if invalid else "false")
        _polish(self)


def labelled(text: str, widget: QWidget) -> QWidget:
    """灰色小标签 + 控件。标签挂在返回值的 .label 上，方便切语言时改。"""
    box = QWidget()
    lay = QHBoxLayout(box)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    lbl = QLabel(text)
    lbl.setObjectName("SmallDim")
    lay.addWidget(lbl)
    lay.addWidget(widget)
    box.label = lbl  # type: ignore[attr-defined]
    return box


def primary_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Primary")
    b.setFixedHeight(CONTROL_H)
    b.setCursor(Qt.PointingHandCursor)
    return b


def button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Btn")
    b.setFixedHeight(CONTROL_H)
    b.setCursor(Qt.PointingHandCursor)
    return b


def ghost_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setObjectName("Ghost")
    b.setFixedHeight(CONTROL_H)
    b.setCursor(Qt.PointingHandCursor)
    return b


def icon_button(kind: str, tooltip: str = "") -> QPushButton:
    b = QPushButton()
    b.setObjectName("IconButton")
    b.setFixedSize(CONTROL_H, CONTROL_H)
    b.setIcon(icons.icon(kind, theme.current().text_dim))
    b.setIconSize(QSize(16, 16))
    b.setCursor(Qt.PointingHandCursor)
    if tooltip:
        b.setToolTip(tooltip)
    return b
