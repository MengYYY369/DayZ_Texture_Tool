"""带列表的页面：拖拽、添加、勾选、开始处理、进度、每行状态。

Game2PBR / PBR2DayZ / 水印 / SMDI 四页都从这里长出来，只换工具条和处理方式。
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import (
    QCoreApplication,
    QObject,
    QRunnable,
    QT_TRANSLATE_NOOP,
    QThreadPool,
    Signal,
)
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QFileDialog, QWidget

from ...models import BatchResult, ProcessingResult
from ..items import DONE, FAILED, RUNNING, SKIPPED, Item, Slot
from ..widgets.issues_panel import IssuesPanel
from ..widgets.list_view import ItemListView
from ..widgets.toolbar import MenuButton, ghost_button
from .base import BasePage

SPLIT_RE = re.compile(r"[,\s]+")


def parse_suffix_text(text: str) -> list[str]:
    """逗号或空格分隔，跟旧界面一个规矩。"""
    return [part for part in SPLIT_RE.split(text.strip()) if part]


def suffix_error(values: list[str]) -> str:
    """检查一组后缀。空串表示没问题，否则是给用户看的原因。"""
    if any("." in value for value in values):
        return QT_TRANSLATE_NOOP("FilePage", "A suffix cannot contain a dot.")
    if len(set(values)) != len(values):
        return QT_TRANSLATE_NOOP("FilePage", "Two slots share the same suffix.")
    return ""


class WorkerSignals(QObject):
    item_done = Signal(str, object)
    finished = Signal()


class Job(QRunnable):
    """一条一条地跑，跑完一条就把结果丢回主线程。"""

    def __init__(self, signals: WorkerSignals, keys: list[str], process) -> None:
        super().__init__()
        self.signals = signals
        self.keys = keys
        self.process = process

    def run(self) -> None:
        for key in self.keys:
            try:
                result = self.process(key)
            except Exception as exc:  # 处理器自己会吞异常，这里只是最后一道
                result = ProcessingResult(False, error=f"{type(exc).__name__}: {exc}")
            self.signals.item_done.emit(key, result)
        self.signals.finished.emit()


class FilePage(BasePage):
    """四页的共同骨架。子类只要给出 build_items / process_key 和工具条。"""

    page_key = ""

    def __init__(
        self,
        settings,
        title: str,
        action_text: str,
        in_width: int = 70,
        in_label: str = "",
        out_label: str = "",
        empty_title: str = "",
        empty_hint: str = "",
        empty_accept: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, action_text, parent)
        self.settings = settings
        self._running = False
        self._results = BatchResult()
        # 表头文字存下来 —— 构造时还没装翻译器，只能在 retranslate() 里再翻一次
        self._in_label = in_label
        self._out_label = out_label

        self.list = ItemListView(
            in_width, in_label, out_label, empty_title, empty_hint, empty_accept
        )
        self.list.files_requested.connect(self.pick_files)
        self.list.folder_requested.connect(self.pick_folder)
        self.list.slot_clicked.connect(self._on_slot)
        self.list.remove_requested.connect(self.remove_checked)
        self.set_body(self.list)

        self.issues = IssuesPanel()
        self.add_footer(self.issues)

        self.add_button = MenuButton(self.tr("Add"))
        self.add_button.set_items(
            [
                (self.tr("Add files"), self.pick_files),
                (self.tr("Add folder"), self.pick_folder),
            ]
        )
        self.remove_button = ghost_button(self.tr("Remove checked"))
        self.remove_button.clicked.connect(self.remove_checked)

        self.status.action_clicked.connect(self.start)
        self.setAcceptDrops(True)

        self._signals = WorkerSignals()
        self._signals.item_done.connect(self._on_item_done)
        self._signals.finished.connect(self._on_finished)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)

    # ---- 子类要实现的 ----

    def retranslate(self) -> None:
        """子类覆盖时记得先调 super()。

        这里不能用 self.tr() —— 它按实例的类名取上下文，GamePage 实例会去找
        GamePage 上下文，而调用点声明的是 QT_TRANSLATE_NOOP("FilePage", ...)。
        """
        self.remove_button.setText(self.tr("Remove checked"))
        self.add_button.set_label(self.tr("Add"))
        self.add_button.set_items(
            [
                (self.tr("Add files"), self.pick_files),
                (self.tr("Add folder"), self.pick_folder),
            ]
        )
        self.list.set_header_labels(
            QCoreApplication.translate("FilePage", self._in_label),
            QCoreApplication.translate("FilePage", self._out_label),
        )

    def build_items(self, paths: list[Path]) -> list[Item]:
        raise NotImplementedError

    def process_key(self, key: str) -> ProcessingResult:
        raise NotImplementedError

    def empty_state_text(self) -> tuple[str, str, str]:
        return ("", "", "")

    def mode_text(self) -> str:
        return ""

    def unit(self) -> str:
        """一行是什么。Game2PBR 一行一个文件，PBR2DayZ 一行一组。"""
        return self.tr("file(s)")

    # ---- 列表 ----

    def add_paths(self, paths: list[Path]) -> int:
        existing = {item.key for item in self.list.items()}
        fresh = [path for path in paths if str(path) not in existing]
        items = self.build_items(fresh)
        if items:
            self.list.model.add_items(items)
            self._save_session()
        self.refresh()
        return len(items)

    def pick_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self, self.tr("Add files"), "", self.file_filter()
        )
        if files:
            self.add_paths([Path(name) for name in files])

    def pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.tr("Add folder"))
        if folder:
            self.add_paths([Path(folder)])

    def file_filter(self) -> str:
        return (
            self.tr("Images")
            + " (*.png *.tga *.tif *.tiff *.jpg *.jpeg *.bmp *.dds *.paa)"
        )

    def add_toolbar_actions(self) -> None:
        """工具条右端收尾：移除 + 添加。五个页面都这么摆。"""
        self.add_toolbar_stretch()
        self.add_toolbar(self.remove_button, self.add_button)

    def _on_slot(self, key: str, index: int) -> None:
        item = self.item_for(key)
        if item is None:
            return
        if index == -3:
            self.remove_item(key)
            return
        if index == -2:
            if item.selectable:
                item.checked = not item.checked
                self.list.view.viewport().update()
                self.refresh()
            return
        self.open_preview(item, index)

    def preview_slots(self, item: Item) -> list[tuple[int, object]]:
        """能点开看大图的格子。输入格编号是下标，输出格编号是 1000 + 下标。"""
        pairs = [(i, slot) for i, slot in enumerate(item.inputs)]
        pairs += [(1000 + i, slot) for i, slot in enumerate(item.outputs)]
        return [
            (code, slot)
            for code, slot in pairs
            if slot.path is not None and not slot.missing
        ]

    def open_preview(self, item: Item, index: int) -> None:
        slots = self.preview_slots(item)
        if not slots:
            return
        codes = [code for code, _ in slots]
        start = codes.index(index) if index in codes else 0
        box = getattr(self.window(), "lightbox", None)
        if box is not None:
            box.show_for(item.title, [slot for _, slot in slots], start)

    def remove_item(self, key: str) -> None:
        self.list.model.remove({key})
        self._save_session()
        self.refresh()

    def remove_checked(self) -> None:
        keys = {item.key for item in self.list.items() if item.checked and item.selectable}
        if not keys:
            self.status.set_status(self.tr("Nothing selected."))
            return
        self.list.model.remove(keys)
        self._save_session()
        self.refresh()

    def item_for(self, key: str) -> Item | None:
        """按 key 找行。

        名字不叫 find —— QWidget.find() 是 Qt 的静态方法，覆盖它会在别的
        调用点静默改变行为。
        """
        for item in self.list.items():
            if item.key == key:
                return item
        return None

    # ---- 拖拽 ----

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile()
        ]
        if paths:
            self.add_paths(paths)
            event.acceptProposedAction()

    # ---- 跑 ----

    def start(self) -> None:
        if self._running:
            return
        items = self.list.checked_items()
        if not items:
            self.status.set_status(self.tr("Nothing selected."))
            return
        self._running = True
        self._results = BatchResult()
        self.status.set_action_enabled(False)
        self.status.set_progress(0, len(items))
        for item in items:
            item.status = RUNNING
            item.status_note = ""
        self.list.view.viewport().update()
        keys = [item.key for item in items]
        self._pool.start(Job(self._signals, keys, self.process_key))

    def _on_item_done(self, key: str, result: ProcessingResult) -> None:
        item = self.item_for(key)
        if item is None:
            return
        self._results.add(result)
        self.apply_result(item, result)
        self._refresh_row(item)

    def apply_result(self, item: Item, result: ProcessingResult) -> None:
        if result.success:
            item.status = DONE
            item.status_note = ""
            item.outputs = [
                Slot(
                    path=path,
                    label=self.output_label(path),
                    size_text=self.size_text(path),
                )
                for path in result.outputs
            ]
            item.output_note = ""
        elif result.error:
            item.status = FAILED
            item.status_note = result.error
        else:
            item.status = SKIPPED
            item.status_note = result.messages[-1] if result.messages else ""

    def _refresh_row(self, item: Item) -> None:
        items = self.list.items()
        for row, existing in enumerate(items):
            if existing is item:
                self.list.model.touch(row)
                break

    def _on_finished(self) -> None:
        self._running = False
        self.status.set_action_enabled(True)
        self.status.reset_progress()
        self.refresh()

    def refresh(self) -> None:
        done = sum(1 for item in self.list.items() if item.status == DONE)
        failed = sum(1 for item in self.list.items() if item.status == FAILED)
        skipped = sum(1 for item in self.list.items() if item.status == SKIPPED)
        total = len(self.list.items())
        if total == 0:
            self.status.set_status(self.mode_text())
        elif self._running:
            self.status.set_status(self.tr("Working..."))
        elif done or failed:
            self.status.set_status(
                self.tr("{done} done · {failed} failed · {skipped} skipped").format(
                    done=done, failed=failed, skipped=skipped
                )
            )
        else:
            self.status.set_status(
                self.tr("{total} {unit} ready").format(total=total, unit=self.unit())
            )
        self._refresh_issues()

    def _refresh_issues(self) -> None:
        failed: list[tuple[str, str]] = []
        skipped: list[tuple[str, str]] = []
        for item in self.list.items():
            if item.status == FAILED:
                failed.append((item.title, item.status_note))
            elif item.status == SKIPPED:
                skipped.append((item.title, item.status_note))
        self.issues.set_issues(failed, skipped)

    # ---- 小工具 ----

    def output_label(self, path: Path) -> str:
        return path.stem

    def size_text(self, path: Path) -> str:
        try:
            return human_size(path.stat().st_size)
        except OSError:
            return ""

    def image_size_text(self, path: Path) -> str:
        """只读文件头拿宽高，不解整张图。"""
        reader = QImageReader(str(path))
        size = reader.size()
        if not size.isValid():
            return ""
        return f"{size.width()} × {size.height()}"

    def set_empty_text(self, title: str, hint: str, accept: str) -> None:
        self.list.empty.retranslate(title, hint, accept)
        self.list.empty.set_mode(self.mode_text())

    # ---- 记忆 ----

    def to_session(self) -> dict:
        return {"keys": [item.key for item in self.list.items()]}

    def load_session(self, payload: dict) -> None:
        keys = payload.get("keys") if isinstance(payload, dict) else None
        if not keys:
            return
        paths = [Path(key) for key in keys if Path(key).exists()]
        if paths:
            self.add_paths(paths)

    def _save_settings(self) -> None:
        # 存盘归外壳管；页面自己单独跑（比如测试里）时没有这个方法。
        save = getattr(self.window(), "save_settings", None)
        if save is not None:
            save()

    def _save_session(self) -> None:
        save = getattr(self.window(), "save_session", None)
        if save is not None:
            save()


def human_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"
