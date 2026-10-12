"""点缩略图弹出来的大图浮层。左右方向键或两侧箭头切换同一行的其它图。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImageReader, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import paa, theme
from ..icons import icon
from .toolbar import icon_button

CARD_W = 660
IMAGE_W = 592
IMAGE_H = 452
STRIP_THUMB = 46


def read_scaled(path: Path, box_w: int, box_h: int) -> QPixmap | None:
    """按需要的尺寸解码，不整张读进内存。"""
    source_path = paa.readable(Path(path))
    if source_path is None:
        return None
    reader = QImageReader(str(source_path))
    size = reader.size()
    if not size.isValid() or size.width() <= 0 or size.height() <= 0:
        return None
    scale = min(box_w / size.width(), box_h / size.height(), 1.0)
    reader.setScaledSize(
        QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale)))
    )
    image = reader.read()
    if image.isNull():
        return None
    return QPixmap.fromImage(image)


class StripThumb(QPushButton):
    """底下那一排小图，当前那张带青色边框。"""

    def __init__(self, label: str, pixmap: QPixmap | None, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("StripThumb")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(STRIP_THUMB + 16, STRIP_THUMB + 24)
        self._pixmap = pixmap
        self._label = QLabel(label, self)
        self._label.setObjectName("TinyMuted")
        self._label.setAlignment(Qt.AlignHCenter)
        self._label.setGeometry(0, STRIP_THUMB + 4, STRIP_THUMB + 16, 16)

    def set_label(self, text: str) -> None:
        self._label.setText(text)

    def paintEvent(self, event) -> None:  # noqa: N802
        t = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        box = self.rect().adjusted(0, 0, 0, -22)
        if self.isChecked():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(self.rect().adjusted(0, 0, 0, 0), 4, 4)
            p.setBrush(QColor(t.content))
            p.drawRoundedRect(box.adjusted(1, 1, -1, -1), 3, 3)
        else:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(t.well))
            p.drawRoundedRect(box, 4, 4)
        if self._pixmap is not None:
            p.drawPixmap(
                box.x() + (box.width() - self._pixmap.width()) // 2,
                box.y() + (box.height() - self._pixmap.height()) // 2,
                self._pixmap,
            )
        p.end()


class Lightbox(QWidget):
    """铺满整个窗口的半透明浮层。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Lightbox")
        self.setFocusPolicy(Qt.StrongFocus)
        self.hide()

        self._slots: list = []
        self._index = 0

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignCenter)

        self.card = QFrame(self)
        self.card.setObjectName("LightboxCard")
        self.card.setFixedWidth(CARD_W)
        outer.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(20, 16, 20, 18)
        lay.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        self.title = QLabel(self.card)
        self.title.setObjectName("SectionTitle")
        head.addWidget(self.title)
        head.addStretch(1)
        self.close_button = icon_button("close", self.tr("Close"))
        self.close_button.clicked.connect(self.hide)
        head.addWidget(self.close_button)
        lay.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(8)
        self.prev_button = icon_button("caret_left", self.tr("Previous"))
        self.prev_button.clicked.connect(lambda: self.step(-1))
        body.addWidget(self.prev_button)

        self.image = QLabel(self.card)
        self.image.setObjectName("LightboxImage")
        self.image.setFixedSize(IMAGE_W, IMAGE_H)
        self.image.setAlignment(Qt.AlignCenter)
        body.addWidget(self.image)

        self.next_button = icon_button("caret_right", self.tr("Next"))
        self.next_button.clicked.connect(lambda: self.step(1))
        body.addWidget(self.next_button)
        lay.addLayout(body)

        self.info = QLabel(self.card)
        self.info.setObjectName("SmallMuted")
        self.info.setAlignment(Qt.AlignHCenter)
        lay.addWidget(self.info)

        self.strip = QHBoxLayout()
        self.strip.setSpacing(6)
        self.strip.setAlignment(Qt.AlignHCenter)
        lay.addLayout(self.strip)

    # ------------------------------------------------------------ 显示

    def show_for(self, title: str, slots: list, index: int = 0) -> None:
        self._slots = [slot for slot in slots if slot.path is not None]
        if not self._slots:
            return
        self._index = max(0, min(index, len(self._slots) - 1))
        self._title = title
        self._rebuild_strip()
        self._refresh()
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()
        self.setFocus(Qt.OtherFocusReason)

    def step(self, delta: int) -> None:
        if not self._slots:
            return
        self._index = (self._index + delta) % len(self._slots)
        self._refresh()

    def _rebuild_strip(self) -> None:
        while self.strip.count():
            item = self.strip.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.deleteLater()
        self._thumbs = []
        for slot in self._slots:
            pixmap = None
            if slot.path is not None and not slot.missing:
                pixmap = read_scaled(slot.path, STRIP_THUMB, STRIP_THUMB)
            thumb = StripThumb(slot.label, pixmap, self.card)
            thumb.clicked.connect(lambda _=False, t=thumb: self._pick(t))
            self.strip.addWidget(thumb)
            self._thumbs.append(thumb)

    def _pick(self, thumb: StripThumb) -> None:
        self._index = self._thumbs.index(thumb)
        self._refresh()

    def _refresh(self) -> None:
        slot = self._slots[self._index]
        self.title.setText(f"{self._title} · {slot.label}")
        pixmap = read_scaled(slot.path, IMAGE_W, IMAGE_H) if slot.path else None
        if pixmap is not None:
            self.image.setPixmap(pixmap)
        else:
            self.image.setText(self.tr("This image cannot be previewed."))
        size = self.image.pixmap().size() if pixmap is not None else QSize()
        bits = [f"{size.width()} × {size.height()}"] if not size.isEmpty() else []
        if slot.size_text:
            bits.append(slot.size_text)
        self.info.setText(" · ".join(bits))
        for i, thumb in enumerate(self._thumbs):
            thumb.setChecked(i == self._index)
        many = len(self._slots) > 1
        self.prev_button.setVisible(many)
        self.next_button.setVisible(many)

    # ------------------------------------------------------------ 事件

    def paintEvent(self, event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 180))
        p.end()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if not self.card.geometry().contains(event.position().toPoint()):
            self.hide()
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key == Qt.Key_Escape:
            self.hide()
        elif key in (Qt.Key_Left, Qt.Key_Up):
            self.step(-1)
        elif key in (Qt.Key_Right, Qt.Key_Down):
            self.step(1)
        else:
            super().keyPressEvent(event)

    def retranslate(self) -> None:
        self.close_button.setToolTip(self.tr("Close"))
        self.prev_button.setToolTip(self.tr("Previous"))
        self.next_button.setToolTip(self.tr("Next"))
        if self._slots:
            self._refresh()
