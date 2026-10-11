"""侧边栏：品牌名 + 四个功能 + 设置 + 语言切换。"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QWidget

from .. import icons
from .. import theme
from ..theme import NAV_H, PAGE_PAD, PT_BODY, PT_SECTION, SIDEBAR_W


class NavItem(QPushButton):
    def __init__(self, icon_kind: str, label: str, active: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setObjectName("NavItem")
        self.setFixedHeight(NAV_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setIconSize(QSize(18, 18))
        self._kind = icon_kind
        self.set_active(active)

    def set_active(self, active: bool) -> None:
        t = theme.current()
        self.setIcon(icons.icon(self._kind, t.accent if active else t.text_dim))
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """四个功能 + 设置 + 语言。选中项左边一条青条。"""

    page_changed = Signal(str)
    language_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(SIDEBAR_W)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        brand = QLabel(self.tr("DayZ Texture Tool"))
        brand.setObjectName("SectionTitle")
        brand.setStyleSheet(f"font-size: {PT_SECTION}pt; font-weight: bold; padding: 18px 0 16px 16px;")
        lay.addWidget(brand)
        self._brand = brand

        self._items: dict[str, NavItem] = {}
        for key, kind, label in [
            ("game", "game", self.tr("Game2PBR")),
            ("pbr", "pbr", self.tr("PBR2DayZ")),
            ("mark", "mark", self.tr("Watermark")),
            ("smdi", "smdi", self.tr("SMDI")),
            ("rvmat", "rvmat", self.tr("RVMAT")),
        ]:
            item = NavItem(kind, label)
            item.clicked.connect(lambda _checked=False, k=key: self.page_changed.emit(k))
            lay.addWidget(item)
            self._items[key] = item

        lay.addStretch(1)

        rule = QFrame()
        rule.setObjectName("HLine")
        rule.setFixedHeight(1)
        rule.setStyleSheet("margin: 0 14px;")
        lay.addWidget(rule)
        lay.addSpacing(6)

        settings_item = NavItem("gear", self.tr("Settings"))
        settings_item.clicked.connect(lambda: self.page_changed.emit("settings"))
        lay.addWidget(settings_item)
        self._items["settings"] = settings_item

        lang = QPushButton("   " + self.tr("中 / EN"))
        lang.setObjectName("LangButton")
        lang.setFixedHeight(30)
        lang.setCursor(Qt.PointingHandCursor)
        lang.setIconSize(QSize(16, 16))
        lang.setIcon(icons.icon("lang", theme.current().text_dim))
        lang.setStyleSheet(f"padding-left: {PAGE_PAD - 6}px; font-size: {PT_BODY}pt;")
        lang.clicked.connect(self.language_requested.emit)
        lay.addWidget(lang)
        lay.addSpacing(10)
        self._lang = lang

        self._current = ""

    def set_current(self, key: str) -> None:
        if key == self._current:
            return
        self._current = key
        for k, item in self._items.items():
            item.set_active(k == key)

    def restyle(self) -> None:
        """主题换了之后，重取一遍被烘进图标的颜色。"""
        t = theme.current()
        self._lang.setIcon(icons.icon("lang", t.text_dim))
        for key, item in self._items.items():
            item.set_active(key == self._current)

    def retranslate(self) -> None:
        self._brand.setText(self.tr("DayZ Texture Tool"))
        self._items["game"].setText(self.tr("Game2PBR"))
        self._items["pbr"].setText(self.tr("PBR2DayZ"))
        self._items["mark"].setText(self.tr("Watermark"))
        self._items["smdi"].setText(self.tr("SMDI"))
        self._items["rvmat"].setText(self.tr("RVMAT"))
        self._items["settings"].setText(self.tr("Settings"))
        self._lang.setText("   " + self.tr("中 / EN"))
