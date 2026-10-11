"""主窗口：侧边栏 + 五个页面。"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QTranslator
from PySide6.QtWidgets import QApplication, QHBoxLayout, QStackedWidget, QWidget

from ..settings import AppSettings, load_settings, save_settings
from . import session, theme
from .pages.game import GamePage
from .pages.mark import MarkPage
from .pages.pbr import PbrPage
from .pages.rvmat import RvmatPage
from .pages.settings import SettingsPage
from .pages.smdi import SmdiPage
from .widgets.lightbox import Lightbox
from .widgets.sidebar import Sidebar

WINDOW_W = 1440
WINDOW_H = 900
MIN_W = 1100
MIN_H = 700


def _translation_dir() -> Path:
    """翻译文件的位置。打包之后 __file__ 在 _MEIPASS 里，同一套算法照样成立。"""
    beside = Path(__file__).resolve().parent / "translations"
    if beside.is_dir():
        return beside
    return Path(getattr(sys, "_MEIPASS", "")) / "dayz_texture_tool" / "ui" / "translations"


TRANSLATION_DIR = _translation_dir()
TRANSLATION_BASE = "dayz_zh_CN"

# 侧边栏顺序 = 页面顺序
PAGE_KEYS = ("game", "pbr", "mark", "smdi", "rvmat", "settings")


class MainWindow(QWidget):
    def __init__(self, settings: AppSettings | None = None) -> None:
        super().__init__()
        self.settings = settings if settings is not None else load_settings()
        self.setObjectName("Root")
        self.setWindowTitle(self.tr("DayZ Texture Tool"))
        self.resize(WINDOW_W, WINDOW_H)
        self.setMinimumSize(MIN_W, MIN_H)

        self.sidebar = Sidebar()
        self.stack = QStackedWidget()
        self.stack.setObjectName("Content")

        self.pages = {
            "game": GamePage(self.settings),
            "pbr": PbrPage(self.settings),
            "mark": MarkPage(self.settings),
            "smdi": SmdiPage(self.settings),
            "rvmat": RvmatPage(self.settings),
            "settings": SettingsPage(self.settings),
        }
        for key in PAGE_KEYS:
            self.stack.addWidget(self.pages[key])

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.sidebar)
        lay.addWidget(self.stack, 1)

        self.sidebar.page_changed.connect(self.show_page)
        self.sidebar.language_requested.connect(self.toggle_language)

        self.lightbox = Lightbox(self)

        self._translator = QTranslator(self)
        self._restore_geometry()
        self.show_page(self.settings.last_page or "game")
        self.apply_language()
        self.load_session()

    # ------------------------------------------------------------ 页面

    def show_page(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.sidebar.set_current(key)
        if self.settings.last_page != key:
            self.settings.last_page = key
            self.save_settings()
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            refresh()

    # ------------------------------------------------------------ 语言

    def toggle_language(self) -> None:
        self.settings.language = "en" if self.settings.language == "zh" else "zh"
        self.save_settings()
        self.apply_language()

    def apply_language(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.removeTranslator(self._translator)
            if self.settings.language == "zh":
                self._translator.load(TRANSLATION_BASE, str(TRANSLATION_DIR))
                app.installTranslator(self._translator)
        self.retranslate()

    def retranslate(self) -> None:
        self.setWindowTitle(self.tr("DayZ Texture Tool"))
        self.sidebar.retranslate()
        for page in self.pages.values():
            page.retranslate()
        self.lightbox.retranslate()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.lightbox.isVisible():
            self.lightbox.setGeometry(self.rect())

    # ------------------------------------------------------------ 主题

    def apply_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        theme.apply(app, self.settings.theme)
        self.sidebar.restyle()
        for widget in self.findChildren(QWidget):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        self.update()

    # ------------------------------------------------------------ 存

    def save_settings(self) -> None:
        save_settings(self.settings)

    def save_session(self) -> None:
        pages = {}
        for key, page in self.pages.items():
            to_session = getattr(page, "to_session", None)
            if callable(to_session):
                pages[key] = to_session()
        session.save({"pages": pages})

    def load_session(self) -> None:
        payload = session.load()
        pages = payload.get("pages") if isinstance(payload, dict) else None
        if not isinstance(pages, dict):
            return
        for key, data in pages.items():
            page = self.pages.get(key)
            load = getattr(page, "load_session", None)
            if callable(load):
                load(data)

    # ------------------------------------------------------------ 窗口

    def _restore_geometry(self) -> None:
        if not self.settings.window_geometry:
            return
        raw = QByteArray.fromBase64(self.settings.window_geometry.encode("ascii"))
        if not raw.isEmpty():
            self.restoreGeometry(raw)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.settings.window_geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        save_settings(self.settings)
        session.clear()
        super().closeEvent(event)
