"""表头 + 行列表 + 空状态。所有页面共用。"""

from __future__ import annotations

from PySide6.QtCore import (
    QAbstractListModel,
    QEvent,
    QModelIndex,
    QRect,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .. import icons
from .. import theme
from ..items import Item
from ..theme import HEADER_H, PT_SMALL, PT_TINY
from ..thumbs import ThumbCache
from .row import CHECK_W, RowDelegate, columns, draw_check
from .toolbar import button, ghost_button


class ItemListModel(QAbstractListModel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._items: list[Item] = []

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or role != Qt.UserRole:
            return None
        return self._items[index.row()]

    def items(self) -> list[Item]:
        return self._items

    def item(self, row: int) -> Item | None:
        return self._items[row] if 0 <= row < len(self._items) else None

    def set_items(self, items: list[Item]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()

    def add_items(self, items: list[Item]) -> None:
        if not items:
            return
        start = len(self._items)
        self.beginInsertRows(QModelIndex(), start, start + len(items) - 1)
        self._items.extend(items)
        self.endInsertRows()

    def replace(self, key: str, item: Item) -> None:
        for row, existing in enumerate(self._items):
            if existing.key == key:
                self._items[row] = item
                self.dataChanged.emit(self.index(row), self.index(row))
                return

    def remove(self, keys: set[str]) -> None:
        keep = [item for item in self._items if item.key not in keys]
        if len(keep) != len(self._items):
            self.set_items(keep)

    def touch(self, row: int) -> None:
        if 0 <= row < len(self._items):
            self.dataChanged.emit(self.index(row), self.index(row))


class ListHeader(QWidget):
    """列表表头。最左边那个方框是全选 —— 旧界面的「清除选中」就是把它取消。"""

    select_all_changed = Signal(bool)

    def __init__(self, in_width: int, in_label: str, out_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ListHeader")
        self.setFixedHeight(HEADER_H)
        self.setCursor(Qt.PointingHandCursor)
        self._in_width = in_width
        self._labels = {"inputs": in_label, "outputs": out_label}
        self._checked = True

    def set_labels(self, in_label: str, out_label: str) -> None:
        self._labels = {"inputs": in_label, "outputs": out_label}
        self.update()

    def set_all(self, checked: bool) -> None:
        self._checked = checked
        self.update()

    def _box_rect(self) -> QRect:
        col = columns(self.width(), self._in_width)
        return QRect(col.check.x() + (CHECK_W - 22) // 2, 0, 22, self.height())

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._box_rect().contains(event.position().toPoint()):
            self._checked = not self._checked
            self.update()
            self.select_all_changed.emit(self._checked)
            return
        super().mousePressEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        col = columns(self.width(), self._in_width)
        draw_check(p, self._box_rect(), self._checked, True, t)
        font = QFont(theme.FAMILY)
        font.setPointSizeF(PT_TINY)
        p.setFont(font)
        p.setPen(QPen(QColor(t.text_muted)))
        fm = QFontMetrics(font)
        for area, text in (
            (col.title, self.tr("File")),
            (col.inputs, self._labels["inputs"]),
            (col.outputs, self._labels["outputs"]),
            (col.size, self.tr("Size")),
            (col.status, self.tr("Status")),
        ):
            if not text:
                continue
            p.drawText(
                QRect(area.x(), 0, area.width() - 10, self.height()),
                Qt.AlignLeft | Qt.AlignVCenter,
                fm.elidedText(text, Qt.ElideRight, area.width() - 10),
            )
        p.end()


class EmptyState(QWidget):
    """空列表时教用户怎么用，不是只报告"没有"。"""

    files_requested = Signal()
    folder_requested = Signal()

    def __init__(self, title: str, hint: str, accept: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        t = theme.current()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(22, 8, 22, 16)
        outer.setSpacing(0)

        box = QFrame()
        box.setObjectName("EmptyBox")
        outer.addWidget(box, 1)

        lay = QVBoxLayout(box)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(8)
        lay.addStretch(1)

        art = QLabel()
        art.setPixmap(icons.pixmap("drop_hint", t.text_muted, 40))
        art.setAlignment(Qt.AlignCenter)
        lay.addWidget(art)
        self._art = art

        self._title = QLabel(title)
        self._title.setObjectName("EmptyTitle")
        self._title.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._title)

        self._hint = QLabel(hint)
        self._hint.setObjectName("SmallDim")
        self._hint.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._hint)

        self._accept = QLabel(accept)
        self._accept.setObjectName("TinyMuted")
        self._accept.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._accept)

        lay.addSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self.files_button = button(self.tr("Add files"))
        self.folder_button = ghost_button(self.tr("Add folder"))
        self.files_button.clicked.connect(self.files_requested.emit)
        self.folder_button.clicked.connect(self.folder_requested.emit)
        row.addWidget(self.files_button)
        row.addWidget(self.folder_button)
        row.addStretch(1)
        lay.addLayout(row)

        lay.addSpacing(10)
        rule = QFrame()
        rule.setObjectName("ThinRule")
        rule.setFixedHeight(1)
        rule.setFixedWidth(320)
        lay.addWidget(rule, 0, Qt.AlignHCenter)

        self._mode = QLabel("")
        self._mode.setObjectName("SmallMuted")
        self._mode.setAlignment(Qt.AlignCenter)
        lay.addWidget(self._mode)
        lay.addStretch(1)

    def set_mode(self, text: str) -> None:
        self._mode.setText(text)

    def restyle(self) -> None:
        self._art.setPixmap(icons.pixmap("drop_hint", theme.current().text_muted, 40))

    def retranslate(self, title: str, hint: str, accept: str) -> None:
        self._title.setText(title)
        self._hint.setText(hint)
        self._accept.setText(accept)
        self.files_button.setText(self.tr("Add files"))
        self.folder_button.setText(self.tr("Add folder"))


class ItemListView(QWidget):
    """表头 + 列表 + 空状态，三选一显示。"""

    slot_clicked = Signal(str, int)
    files_requested = Signal()
    folder_requested = Signal()
    header_toggled = Signal(bool)
    remove_requested = Signal()

    def __init__(
        self,
        in_width: int = 70,
        in_label: str = "",
        out_label: str = "",
        empty_title: str = "",
        empty_hint: str = "",
        empty_accept: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.cache = ThumbCache(parent=self)
        self.model = ItemListModel(self)
        self.delegate = RowDelegate(self.cache, in_width, self)
        self.delegate.slot_clicked.connect(self.slot_clicked.emit)
        self.cache.ready.connect(self._refresh)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.header = ListHeader(in_width, in_label, out_label)
        lay.addWidget(self.header)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        self.view = QListView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(self.delegate)
        self.view.setUniformItemSizes(True)
        self.view.setLayoutMode(QListView.Batched)
        self.view.setBatchSize(40)
        self.view.setMouseTracking(True)
        self.view.setSelectionMode(QListView.NoSelection)
        self.view.setEditTriggers(QListView.NoEditTriggers)
        self.view.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view.setFrameShape(QFrame.NoFrame)
        self.view.setSpacing(0)
        # 列表本身接不到 Delete —— 键盘事件进的是 QListView 那个子控件
        self.view.installEventFilter(self)
        self.stack.addWidget(self.view)

        self.empty = EmptyState(empty_title, empty_hint, empty_accept)
        self.empty.files_requested.connect(self.files_requested.emit)
        self.empty.folder_requested.connect(self.folder_requested.emit)
        self.stack.addWidget(self.empty)

        self.model.rowsInserted.connect(self._sync)
        self.model.rowsRemoved.connect(self._sync)
        self.model.modelReset.connect(self._sync)
        self.header.select_all_changed.connect(self.set_all_checked)
        self._sync()

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.view and event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_Delete:
                self.remove_requested.emit()
                return True
        return super().eventFilter(obj, event)

    def _refresh(self, _key: str = "") -> None:
        self.view.viewport().update()

    def _sync(self) -> None:
        empty = self.model.rowCount() == 0
        self.header.setVisible(not empty)
        self.stack.setCurrentWidget(self.empty if empty else self.view)

    def items(self) -> list[Item]:
        return self.model.items()

    def set_header_labels(self, in_label: str, out_label: str) -> None:
        """换表头文字。切语言时用。"""
        self.header.set_labels(in_label, out_label)

    def set_items(self, items: list[Item]) -> None:
        self.model.set_items(items)

    def checked_items(self) -> list[Item]:
        return [item for item in self.model.items() if item.checked and item.selectable]

    def set_all_checked(self, checked: bool) -> None:
        for item in self.model.items():
            if item.selectable:
                item.checked = checked
        self.view.viewport().update()
        self.header_toggled.emit(checked)
