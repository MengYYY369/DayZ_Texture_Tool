"""Game2PBR：一张进，一到四张出。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QT_TRANSLATE_NOOP

from ...batch import collect_image_files, detect_game2pbr_processor
from ...models import ProcessingResult
from ...processors.game2pbr import process_game2pbr
from ...settings import DEFAULT_GAME_OUTPUT_SUFFIXES, DEFAULT_GAME_SUFFIXES
from ..items import PENDING, SKIPPED, Item, Slot
from ..widgets.toolbar import Combo, Field, Segmented, Toggle, ghost_button, labelled
from .file_page import FilePage, parse_suffix_text, suffix_error

# (处理模式, 下拉里显示的名字, 输出的槽位顺序 —— 顺序必须跟处理器函数返回的顺序一致)
MODES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "DF_NRM",
        QT_TRANSLATE_NOOP("GamePage", "Delta Force NRM mode (3 outputs)"),
        ("metal", "roughness", "normal"),
    ),
    (
        "DF_MRA",
        QT_TRANSLATE_NOOP("GamePage", "Delta Force MRA mode (3 outputs)"),
        ("metal", "roughness", "ao"),
    ),
    (
        "ABI_ORN",
        QT_TRANSLATE_NOOP("GamePage", "Arena Breakout ORN mode (3 outputs)"),
        ("roughness", "ao", "normal"),
    ),
    (
        "SplitColorAlphaProcessor",
        QT_TRANSLATE_NOOP("GamePage", "Split color and alpha (2 outputs)"),
        ("rgb", "alpha"),
    ),
    (
        "SplitRGBAProcessor",
        QT_TRANSLATE_NOOP("GamePage", "Split RGBA channels (4 outputs)"),
        ("r", "g", "b", "a"),
    ),
    (
        "MergeRGBAProcessor",
        QT_TRANSLATE_NOOP("GamePage", "Merge RGB and alpha (1 output)"),
        ("merged",),
    ),
    (
        "XYNormalMapProcessor",
        QT_TRANSLATE_NOOP("GamePage", "Rebuild XY normal map (1 output)"),
        ("normal",),
    ),
    (
        "DirectConvertProcessor",
        QT_TRANSLATE_NOOP("GamePage", "Direct convert mode (1 output)"),
        ("converted",),
    ),
    (
        "DirectinvertProcessor",
        QT_TRANSLATE_NOOP("GamePage", "Direct invert mode (1 output)"),
        ("inverted",),
    ),
]

SLOT_NAMES = {
    "rgb": "RGB",
    "alpha": "Alpha",
    "r": "R",
    "g": "G",
    "b": "B",
    "a": "A",
    "merged": "Merged",
    "normal": "Normal",
    "converted": "Converted",
    "inverted": "Inverted",
    "metal": "Metal",
    "roughness": "Rough",
    "ao": "AO",
}


class GamePage(FilePage):
    page_key = "game"

    def __init__(self, settings, parent=None) -> None:
        super().__init__(
            settings,
            title="Game2PBR",
            action_text="Start",
            in_width=70,
            in_label=QT_TRANSLATE_NOOP("FilePage", "Source"),
            out_label=QT_TRANSLATE_NOOP("FilePage", "Output"),
            empty_title="Drop textures here",
            empty_hint="A whole folder works too — files are grouped by the suffix you pick.",
            empty_accept="PNG · TGA · TIF · JPG · BMP · DDS",
            parent=parent,
        )
        self.mode_combo = Combo(
            [(key, self.tr(label)) for key, label, _ in MODES], width=300
        )
        self.mode_combo.changed.connect(self._on_mode)
        self.match = Segmented(
            [("exact", self.tr("Exact")), ("fuzzy", self.tr("Fuzzy"))],
            active=0,
            width=130,
        )
        self.match.set_value(settings.game_match_mode, notify=False)
        self.match.changed.connect(self._on_match)
        self.delete_source = Toggle(self.tr("Delete src"), on=True)
        self.suffix_field = Field(" ".join(self.match_suffixes()), 150)
        self.suffix_field.editingFinished.connect(self._on_suffixes)
        self.suffix_box = labelled(self.tr("Match suffix"), self.suffix_field)
        self.by_suffix = ghost_button(self.tr("Select by suffix"))
        self.by_suffix.clicked.connect(self.select_by_suffix)

        self.add_toolbar(
            self.mode_combo,
            self.match,
            self.delete_source,
            self.suffix_box,
            self.by_suffix,
        )
        self.add_toolbar_actions()

        self.set_empty_text(
            self.tr("Drop textures here"),
            self.tr(
                "A whole folder works too — files are grouped by the suffix you pick."
            ),
            "PNG · TGA · TIF · JPG · BMP · DDS",
        )

    # ---- 当前模式 ----

    def mode(self) -> tuple[str, str, tuple[str, ...]]:
        key = self.mode_combo.value()
        return next((entry for entry in MODES if entry[0] == key), MODES[0])

    def slots(self) -> tuple[str, ...]:
        return self.mode()[2]

    def match_suffixes(self) -> list[str]:
        processor = self.mode()[0]
        return self.settings.game_suffixes.get(
            processor, DEFAULT_GAME_SUFFIXES.get(processor, [])
        )

    def output_suffixes(self) -> dict[str, str]:
        processor = self.mode()[0]
        return self.settings.game_output_suffixes.get(
            processor, DEFAULT_GAME_OUTPUT_SUFFIXES.get(processor, {})
        )

    def mode_text(self) -> str:
        return self.tr("Mode: {mode} · matches {suffixes}").format(
            mode=self.tr(self.mode()[1]),
            suffixes=" ".join(self.match_suffixes()) or "—",
        )

    # ---- 工具条 ----

    def _on_mode(self, _value: str) -> None:
        self._save_settings()
        self._show_suffixes()
        self._reclassify()
        self.list.empty.set_mode(self.mode_text())
        self.refresh()

    def _show_suffixes(self) -> None:
        """把当前模式的识别后缀摆进工具条那个框。"""
        self.suffix_field.set_invalid(False)
        self.suffix_field.setText(" ".join(self.match_suffixes()))

    def _on_suffixes(self) -> None:
        values = parse_suffix_text(self.suffix_field.text())
        error = suffix_error(values)
        self.suffix_field.set_invalid(bool(error))
        if error:
            self.status.set_status(QCoreApplication.translate("FilePage", error))
            return
        self.settings.game_suffixes[self.mode()[0]] = values
        self._save_settings()
        self._reclassify()
        self.list.empty.set_mode(self.mode_text())
        self.refresh()

    def _on_match(self, value: str) -> None:
        self.settings.game_match_mode = value
        self._save_settings()
        self._reclassify()
        self.refresh()

    def _save_settings(self) -> None:
        window = self.window()
        if hasattr(window, "save_settings"):
            window.save_settings()

    def select_by_suffix(self) -> None:
        """按当前模式的识别后缀，把匹配上的行全勾上。"""
        matched = 0
        for item in self.list.items():
            if item.selectable:
                item.checked = self.matches(Path(self.source_of(item.key)))
                matched += 1 if item.checked else 0
        self.list.header.set_all(
            matched == len(self.list.checked_items()) and matched > 0
        )
        self.list.view.viewport().update()
        self.refresh()

    # ---- 行 ----

    def matches(self, path: Path) -> bool:
        processor = self.mode()[0]
        return (
            detect_game2pbr_processor(
                path, {processor: self.match_suffixes()}, self.match.value()
            )
            is not None
        )

    def build_items(self, paths: list[Path]) -> list[Item]:
        items = []
        for path in paths:
            for found in collect_image_files(path):
                items.append(self._make_item(found))
        return items

    def _make_item(self, path: Path) -> Item:
        item = Item(
            key=self.next_key(str(path)), title=path.name, subtitle=path.parent.name
        )
        item.source = str(path)
        item.size_top = self.image_size_text(path)
        item.size_bottom = self.size_text(path)
        self._classify(item, path)
        return item

    def _classify(self, item: Item, path: Path) -> None:
        item.inputs = [
            Slot(label=self.tr("Source"), path=path, size_text=item.size_bottom)
        ]
        if self.matches(path):
            item.status = PENDING
            item.status_note = ""
            item.selectable = True
            item.checked = True
            # 先把空槽位摆出来，让人在按开始之前就看见这一张会出几张
            item.outputs = [
                Slot(label=SLOT_NAMES.get(key, key), missing=True)
                for key in self.slots()
            ]
        else:
            item.status = SKIPPED
            item.status_note = self.tr("Name doesn't match this mode's suffix.")
            item.selectable = False
            item.checked = False
            item.outputs = []

    def _reclassify(self) -> None:
        """换了模式或匹配方式之后，还没跑过的行重新判一次。"""
        for item in self.list.items():
            if item.status in (PENDING, SKIPPED):
                self._classify(item, Path(self.source_of(item.key)))
        self.list.view.viewport().update()

    # ---- 跑 ----

    def process_key(self, key: str) -> ProcessingResult:
        return process_game2pbr(
            self.source_of(key),
            self.mode()[0],
            delete_source=self.delete_source.isChecked(),
            output_suffixes=self.output_suffixes(),
        )

    def output_label(self, path: Path) -> str:
        return self._label_for(path)

    def _label_for(self, path: Path) -> str:
        suffixes = self.output_suffixes()
        for slot in self.slots():
            suffix = suffixes.get(slot, "")
            if suffix and path.stem.endswith(suffix):
                return SLOT_NAMES.get(slot, slot)
        return path.stem

    # ---- 语言 ----

    def retranslate(self) -> None:
        super().retranslate()
        self.title_label.setText(self.tr("Game2PBR"))
        self.status.set_action_text(self.tr("Start"))
        self.delete_source.set_label(self.tr("Delete src"))
        self.suffix_box.label.setText(self.tr("Match suffix"))
        self.by_suffix.setText(self.tr("Select by suffix"))
        self.mode_combo.set_items([(key, self.tr(label)) for key, label, _ in MODES])
        self.match.set_labels([self.tr("Exact"), self.tr("Fuzzy")])
        self.set_empty_text(
            self.tr("Drop textures here"),
            self.tr(
                "A whole folder works too — files are grouped by the suffix you pick."
            ),
            "PNG · TGA · TIF · JPG · BMP · DDS",
        )
        self.refresh()
