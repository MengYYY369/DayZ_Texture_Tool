"""一行怎么画，以及每一列在哪。

列：勾选框 | 文件名 | 变换前 | → | 变换后 | 分栏线 | 尺寸/大小 | 状态
「变换前」的宽度按页固定（Game2PBR 70 = 1 张，PBR2DayZ 358 = 5 张），
这样整页里箭头和「变换后」的横坐标是恒定的。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QEvent, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from .. import theme
from ..items import DONE, FAILED, PENDING, RUNNING, SKIPPED
from ..thumbs import ThumbCache
from ..theme import PT_BODY, PT_MICRO, PT_SMALL, PT_TINY, ROW_H, THUMB

CHECK_W = 30
TITLE_W = 184
ARROW_W = 30
SIZE_W = 142
STATUS_W = 130
PAD_L = 12
PAD_R = 16
GAP = 16
CELL_W = 70
CELL_SPACING = 2
V_MARGIN = 8

STATUS_COLORS = {
    PENDING: "text_muted",
    RUNNING: "accent",
    DONE: "ok",
    FAILED: "err",
    SKIPPED: "skip",
}
STATUS_TEXT = {
    PENDING: "Pending",
    RUNNING: "Working",
    DONE: "Done",
    FAILED: "Failed",
    SKIPPED: "Skipped",
}


@dataclass(frozen=True)
class Columns:
    check: QRect
    title: QRect
    inputs: QRect
    arrow: QRect
    outputs: QRect
    rule: QRect
    size: QRect
    status: QRect


def columns(width: int, in_width: int) -> Columns:
    x = PAD_L
    check = QRect(x, 0, CHECK_W, 0)
    x += CHECK_W
    title = QRect(x, 0, TITLE_W, 0)
    x += TITLE_W
    inputs = QRect(x, 0, in_width, 0)
    x += in_width
    arrow = QRect(x, 0, ARROW_W, 0)
    x += ARROW_W
    outputs_w = max(0, width - x - (1 + GAP + SIZE_W + STATUS_W + PAD_R))
    outputs = QRect(x, 0, outputs_w, 0)
    x += outputs_w
    rule = QRect(x, 0, 1, 0)
    x += 1 + GAP
    size = QRect(x, 0, SIZE_W, 0)
    x += SIZE_W
    status = QRect(x, 0, STATUS_W, 0)
    return Columns(check, title, inputs, arrow, outputs, rule, size, status)


def cell_rects(area: QRect, count: int) -> list[QRect]:
    """把一格里的小图从左往右排。"""
    if count <= 0:
        return []
    total = count * CELL_W + (count - 1) * CELL_SPACING
    x = area.x() + max(0, (area.width() - total) // 2)
    rects = []
    for i in range(count):
        rects.append(QRect(x + i * (CELL_W + CELL_SPACING), area.y(), CELL_W, area.height()))
    return rects


def _font(size: float, bold: bool = False) -> QFont:
    f = QFont(theme.FAMILY)
    f.setPointSizeF(size)
    f.setBold(bold)
    return f


def draw_check(painter: QPainter, rect: QRect, checked: bool, enabled: bool, t) -> None:
    painter.save()
    box = QRect(rect.x() + (rect.width() - 15) // 2, rect.y() + (rect.height() - 15) // 2, 15, 15)
    painter.setRenderHint(QPainter.Antialiasing)
    if checked and enabled:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t.accent))
        painter.drawRoundedRect(box, 3, 3)
        pen = QPen(QColor(t.accent_ink))
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        path = QPainterPath()
        path.moveTo(box.x() + 3.4, box.y() + 7.6)
        path.lineTo(box.x() + 6.3, box.y() + 10.6)
        path.lineTo(box.x() + 11.6, box.y() + 4.4)
        painter.drawPath(path)
    else:
        painter.setPen(QPen(QColor(t.line_strong if enabled else t.line), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRect(box.x(), box.y(), box.width() - 1, box.height() - 1), 3, 3)
    painter.restore()


def _draw_cell(painter: QPainter, area: QRect, slot, cache: ThumbCache, source: bool, t, dim: bool = False) -> None:
    box = QRect(area.x(), area.y(), THUMB, THUMB)
    if slot.missing or slot.path is None:
        painter.setPen(QPen(QColor(t.line), 1, Qt.DashLine))
        painter.setBrush(QColor(t.well))
        painter.drawRect(box)
        painter.setPen(QPen(QColor(t.text_muted)))
        painter.setFont(_font(PT_MICRO))
        # 空槽里也认 placeholder：没跑之前那三个格显示 _worn / _damage / _destruct，
        # 没勾的那个 placeholder 是空串，就还是画 "—"。
        painter.drawText(box, Qt.AlignCenter, slot.placeholder or "—")
    else:
        pixmap = cache.get(slot.path)
        painter.setPen(QPen(QColor(t.line_strong), 1) if source else Qt.NoPen)
        painter.setBrush(QColor(t.well_in if source else t.well))
        painter.drawRect(box)
        if pixmap is not None:
            target = QRect(
                box.x() + (box.width() - pixmap.width()) // 2,
                box.y() + (box.height() - pixmap.height()) // 2,
                pixmap.width(),
                pixmap.height(),
            )
            if dim:
                painter.setOpacity(0.4)
            painter.drawPixmap(target, pixmap)
            painter.setOpacity(1.0)
        elif cache.finished(slot.path):
            painter.setPen(QPen(QColor(t.text_muted)))
            painter.setFont(_font(PT_MICRO))
            text = slot.placeholder or slot.path.suffix.lstrip(".").upper()[:4] or "?"
            painter.drawText(box, Qt.AlignCenter, text)

    painter.setPen(QPen(QColor(t.text_dim if not source else t.text_muted)))
    painter.setFont(_font(PT_TINY))
    painter.drawText(
        QRect(area.x(), box.bottom() + 2, CELL_W, 13),
        Qt.AlignHCenter | Qt.AlignTop,
        QFontMetrics(painter.font()).elidedText(slot.label, Qt.ElideRight, CELL_W),
    )
    if slot.size_text:
        painter.setPen(QPen(QColor(t.text_muted)))
        painter.setFont(_font(PT_MICRO))
        painter.drawText(QRect(area.x(), box.bottom() + 15, CELL_W, 12), Qt.AlignHCenter | Qt.AlignTop, slot.size_text)


class RowDelegate(QStyledItemDelegate):
    """按需绘制一行。不用控件，500 行也不卡。"""

    slot_clicked = Signal(str, int)  # 行的 key, 第几格（-1 表示输入格）

    def __init__(self, cache: ThumbCache, in_width: int, parent=None) -> None:
        super().__init__(parent)
        self.cache = cache
        self.in_width = in_width

    def sizeHint(self, option, index) -> QSize:  # noqa: N802
        return QSize(option.rect.width(), ROW_H)

    # ------------------------------------------------------------ 绘制
    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        t = theme.current()
        item = index.data(Qt.UserRole)
        rect = option.rect
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        hovered = bool(option.state & QStyle.State_MouseOver)
        painter.fillRect(rect, QColor(t.row_hover if hovered else t.content))
        painter.setPen(QPen(QColor(t.line)))
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())

        col = columns(rect.width(), self.in_width)
        top = rect.top() + V_MARGIN
        inner_h = rect.height() - V_MARGIN * 2

        # 勾选框
        draw_check(painter, QRect(rect.x() + col.check.x(), top, CHECK_W, inner_h), item.checked, item.selectable, t)

        # 文件名 + 元信息
        title_area = QRect(rect.x() + col.title.x(), top, TITLE_W - 10, inner_h)
        painter.setPen(QPen(QColor(t.text_muted if not item.selectable else t.text)))
        painter.setFont(_font(PT_BODY))
        fm = QFontMetrics(painter.font())
        painter.drawText(
            QRect(title_area.x(), title_area.y() + inner_h // 2 - 18, title_area.width(), 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            fm.elidedText(item.title, Qt.ElideMiddle, title_area.width()),
        )
        painter.setPen(QPen(QColor(t.text_muted)))
        painter.setFont(_font(PT_TINY))
        painter.drawText(
            QRect(title_area.x(), title_area.y() + inner_h // 2 + 2, title_area.width(), 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            fm.elidedText(item.subtitle, Qt.ElideRight, title_area.width()),
        )

        # 变换前
        cell_h = 64 + 15 + 12
        cell_y = top + (inner_h - cell_h) // 2
        for slot, area in zip(
            item.inputs,
            cell_rects(QRect(rect.x() + col.inputs.x(), cell_y, col.inputs.width(), cell_h), len(item.inputs)),
        ):
            _draw_cell(painter, area, slot, self.cache, True, t, dim=not item.selectable)

        # 箭头
        painter.setPen(QPen(QColor(t.text_muted)))
        painter.setFont(_font(12))
        painter.drawText(
            QRect(rect.x() + col.arrow.x(), top, ARROW_W, inner_h), Qt.AlignCenter, "→"
        )

        # 变换后
        out_area = QRect(rect.x() + col.outputs.x(), cell_y, col.outputs.width(), cell_h)
        if item.outputs:
            for slot, area in zip(item.outputs, cell_rects(out_area, len(item.outputs))):
                _draw_cell(painter, area, slot, self.cache, False, t, dim=not item.selectable)
        elif item.output_note:
            painter.setPen(QPen(QColor(t.text_muted)))
            painter.setFont(_font(PT_SMALL))
            painter.drawText(
                QRect(out_area.x(), top, out_area.width(), inner_h),
                Qt.AlignLeft | Qt.AlignVCenter,
                QFontMetrics(painter.font()).elidedText(item.output_note, Qt.ElideRight, out_area.width()),
            )

        # 分栏线
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(t.line_strong))
        painter.drawRect(QRect(rect.x() + col.rule.x(), top + 12, 1, inner_h - 24))

        # 尺寸 / 大小
        size_area = QRect(rect.x() + col.size.x(), top, SIZE_W - 10, inner_h)
        painter.setPen(QPen(QColor(t.text_dim if item.selectable else t.text_muted)))
        painter.setFont(_font(PT_SMALL))
        painter.drawText(
            QRect(size_area.x(), size_area.y() + inner_h // 2 - 18, size_area.width(), 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(painter.font()).elidedText(item.size_top, Qt.ElideRight, size_area.width()),
        )
        painter.setPen(QPen(QColor(t.text_muted)))
        painter.setFont(_font(PT_TINY))
        painter.drawText(
            QRect(size_area.x(), size_area.y() + inner_h // 2 + 2, size_area.width(), 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            QFontMetrics(painter.font()).elidedText(item.size_bottom, Qt.ElideRight, size_area.width()),
        )

        # 状态
        status_area = QRect(rect.x() + col.status.x(), top, STATUS_W - 8, inner_h)
        color = getattr(t, STATUS_COLORS.get(item.status, "text_muted"))
        label = self.tr(STATUS_TEXT.get(item.status, ""))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRect(status_area.x(), status_area.y() + inner_h // 2 - 14, 7, 7))
        painter.setPen(QPen(QColor(color if item.status in (FAILED, SKIPPED) else t.text)))
        painter.setFont(_font(PT_BODY))
        painter.drawText(
            QRect(status_area.x() + 13, status_area.y() + inner_h // 2 - 20, status_area.width() - 13, 16),
            Qt.AlignLeft | Qt.AlignVCenter,
            label,
        )
        if item.status_note:
            painter.setPen(QPen(QColor(t.text_muted)))
            painter.setFont(_font(PT_MICRO))
            painter.drawText(
                QRect(status_area.x(), status_area.y() + inner_h // 2 - 2, status_area.width(), 30),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                item.status_note,
            )
        painter.restore()

    # ------------------------------------------------------------ 交互
    def editorEvent(self, event, model, option, index):  # noqa: N802
        if event.type() != QEvent.MouseButtonRelease or event.button() != Qt.LeftButton:
            return False
        item = index.data(Qt.UserRole)
        rect = option.rect
        col = columns(rect.width(), self.in_width)
        top = rect.top() + V_MARGIN
        inner_h = rect.height() - V_MARGIN * 2
        cell_h = 64 + 15 + 12
        cell_y = top + (inner_h - cell_h) // 2
        pos = event.position().toPoint()

        if QRect(rect.x() + col.check.x(), top, CHECK_W, inner_h).contains(pos) and item.selectable:
            self.slot_clicked.emit(item.key, -2)
            return True

        for base, slots, is_input in ((col.inputs, item.inputs, True), (col.outputs, item.outputs, False)):
            for i, area in enumerate(cell_rects(QRect(rect.x() + base.x(), cell_y, base.width(), cell_h), len(slots))):
                if area.contains(pos) and slots[i].path is not None:
                    self.slot_clicked.emit(item.key, i if is_input else 1000 + i)
                    return True
        return False
