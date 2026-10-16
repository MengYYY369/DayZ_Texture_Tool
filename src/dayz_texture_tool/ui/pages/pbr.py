"""PBR2DayZ：五张 PBR 贴图一组，最多出四张。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP

from ...models import ProcessingResult
from ...processors.pbr2dayz import (
    PBRGroup,
    convert_pbr_group,
    root_context_for_files,
    scan_pbr_paths,
)
from ..items import DONE, FAILED, PENDING, RUNNING, SKIPPED, Item, Slot
from ..widgets.toolbar import Combo, Field, Segmented, Toggle, labelled
from .file_page import FilePage, human_size

PBR_TYPES = ["basecolor", "normal", "roughness", "metallic", "ao"]
OUTPUT_TYPES = ["co", "nohq", "smdi", "as"]

# 哪一张输出需要哪一种输入
OUTPUT_NEEDS = {"co": "basecolor", "nohq": "normal", "smdi": "roughness", "as": "ao"}

TYPE_LABELS = {
    "basecolor": QT_TRANSLATE_NOOP("PbrPage", "Base color"),
    "normal": QT_TRANSLATE_NOOP("PbrPage", "Normal"),
    "roughness": QT_TRANSLATE_NOOP("PbrPage", "Roughness"),
    "metallic": QT_TRANSLATE_NOOP("PbrPage", "Metallic"),
    "ao": QT_TRANSLATE_NOOP("PbrPage", "AO"),
}

OUTPUT_LABELS = {
    "co": QT_TRANSLATE_NOOP("PbrPage", "CO"),
    "nohq": QT_TRANSLATE_NOOP("PbrPage", "NOHQ"),
    "smdi": QT_TRANSLATE_NOOP("PbrPage", "SMDI"),
    "as": QT_TRANSLATE_NOOP("PbrPage", "AS"),
}

PREFIX_MODES = [
    ("auto", QT_TRANSLATE_NOOP("PbrPage", "Prefix: Auto")),
    ("current_folder", QT_TRANSLATE_NOOP("PbrPage", "Prefix: Folder name")),
    ("parent_folder", QT_TRANSLATE_NOOP("PbrPage", "Prefix: Parent folder")),
    ("filename_prefix", QT_TRANSLATE_NOOP("PbrPage", "Prefix: From filename")),
    ("custom", QT_TRANSLATE_NOOP("PbrPage", "Prefix: Custom")),
]

RESOLUTIONS = ["auto", "256", "512", "1024", "2048"]


class PbrPage(FilePage):
    page_key = "pbr"

    def __init__(self, settings, parent=None) -> None:
        super().__init__(
            settings,
            title="PBR2DayZ",
            action_text="Start",
            in_width=358,
            in_label=QT_TRANSLATE_NOOP("FilePage", "Source · 5 per group"),
            out_label=QT_TRANSLATE_NOOP("FilePage", "Output · up to 4"),
            empty_title="Drop PBR texture sets here",
            empty_hint="Files in the same folder that share a prefix become one group.",
            empty_accept="basecolor · normal · roughness · metallic · ao",
            parent=parent,
        )
        self._groups: dict[str, PBRGroup] = {}

        self.normal_type = Segmented(
            [("directx", "DirectX"), ("opengl", "OpenGL")], active=0, width=150
        )
        self.resolution = Combo(
            [
                (value, value if value != "auto" else self.tr("Auto"))
                for value in RESOLUTIONS
            ],
            width=110,
        )
        self.prefix_mode = Combo(
            [(value, self.tr(label)) for value, label in PREFIX_MODES], width=160
        )
        self.prefix_mode.set_value(settings.pbr_prefix_mode, notify=False)
        self.custom_prefix = Field(settings.pbr_custom_prefix, 120)
        self.custom_prefix.setPlaceholderText(self.tr("Custom prefix"))
        self.custom_prefix.editingFinished.connect(self._on_custom_prefix)
        self.match = Segmented(
            [("exact", self.tr("Exact")), ("fuzzy", self.tr("Fuzzy"))],
            active=1,
            width=130,
        )
        self.match.set_value(settings.pbr_match_mode, notify=False)
        self.match.changed.connect(self._on_match)
        self.prefix_mode.changed.connect(self._on_prefix_mode)
        self.make_paa = Toggle(self.tr("PAA"), on=True)
        self.add_watermark = Toggle(self.tr("Watermark"))
        self.delete_source = Toggle(self.tr("Delete src"), on=True)

        self._normal_box = labelled(self.tr("Normal"), self.normal_type)
        self._resolution_box = labelled(self.tr("Resolution"), self.resolution)
        self.add_toolbar(
            self._normal_box,
            self._resolution_box,
            self.prefix_mode,
            self.custom_prefix,
            self.match,
            self.make_paa,
            self.add_watermark,
            self.delete_source,
        )
        self.add_toolbar_actions()

        self.set_empty_text(
            self.tr("Drop PBR texture sets here"),
            self.tr("Files in the same folder that share a prefix become one group."),
            "basecolor · normal · roughness · metallic · ao",
        )
        self._sync_custom_prefix()

    # ---- 工具条 ----

    def _on_match(self, value: str) -> None:
        self.settings.pbr_match_mode = value
        self._save_settings()
        self._rebuild()

    def _on_prefix_mode(self, value: str) -> None:
        self.settings.pbr_prefix_mode = value
        self._save_settings()
        self._sync_custom_prefix()
        self._rebuild()

    def _on_custom_prefix(self) -> None:
        self.settings.pbr_custom_prefix = self.custom_prefix.text()
        self._save_settings()
        if self.settings.pbr_prefix_mode == "custom":
            self._rebuild()

    def _sync_custom_prefix(self) -> None:
        custom = self.settings.pbr_prefix_mode == "custom"
        self.custom_prefix.setEnabled(custom)
        self.custom_prefix.setVisible(custom)

    def _save_settings(self) -> None:
        window = self.window()
        if hasattr(window, "save_settings"):
            window.save_settings()

    def unit(self) -> str:
        return self.tr("group(s)")

    def mode_text(self) -> str:
        return self.tr("Grouped by folder + prefix · {count} group(s)").format(
            count=len(self.list.items())
        )

    # ---- 行 ----

    def build_items(self, paths: list[Path]) -> list[Item]:
        files: list[Path] = []
        for path in paths:
            if path.is_dir():
                files.extend(
                    sorted(child for child in path.rglob("*") if child.is_file())
                )
            elif path.is_file():
                files.append(path)
        if not files:
            return []
        groups = scan_pbr_paths(
            files,
            root_context_for_files(files),
            self.settings.pbr_suffixes,
            self.settings.pbr_match_mode,
            self.settings.pbr_prefix_mode,
            self.settings.pbr_custom_prefix,
        )
        items = []
        for group in groups:
            item = self._make_item(group)
            self._groups[item.key] = group
            items.append(item)
        return items

    def _rebuild(self) -> None:
        """换了前缀 / 匹配方式：重算还没跑的行，跑过的行冻着不动。"""
        frozen = [
            item for item in self.list.items() if item.status in (DONE, FAILED, RUNNING)
        ]
        files: list[Path] = []
        for item in self.list.items():
            if item.status in (PENDING, SKIPPED):
                files.extend(slot.path for slot in item.inputs if slot.path is not None)
        items = self.build_items(files) + frozen
        keys = {item.key for item in items}
        self._groups = {
            key: group for key, group in self._groups.items() if key in keys
        }
        self.list.set_items(items)
        self.list.empty.set_mode(self.mode_text())

    def _make_item(self, group: PBRGroup) -> Item:
        key = self.next_key(f"{group.directory}|{group.prefix}")
        # 前缀就是文件夹名时，副标题改用上一层，免得两行写一样的字
        folder = group.directory.name
        subtitle = folder if folder != group.prefix else group.directory.parent.name
        item = Item(key=key, title=group.prefix, subtitle=subtitle)
        item.inputs = [
            Slot(
                label=self.tr(TYPE_LABELS[tex_type]),
                path=group.textures.get(tex_type),
                size_text=self.size_text(group.textures[tex_type])
                if tex_type in group.textures
                else "",
                missing=tex_type not in group.textures,
            )
            for tex_type in PBR_TYPES
        ]
        item.outputs = [
            Slot(label=self.tr(OUTPUT_LABELS[out]), path=None, missing=True)
            for out in OUTPUT_TYPES
        ]
        usable = [out for out, need in OUTPUT_NEEDS.items() if need in group.textures]
        item.size_top = self.image_size_text(next(iter(group.textures.values())))
        item.size_bottom = human_size(
            sum(self._file_size(path) for path in group.textures.values())
        )
        if usable:
            item.status = PENDING
            item.checked = True
            item.selectable = True
        else:
            item.status = SKIPPED
            item.status_note = self.tr("Skipped: no convertible textures.")
            item.checked = False
            item.selectable = False
        return item

    def _file_size(self, path: Path) -> int:
        try:
            return path.stat().st_size
        except OSError:
            return 0

    # ---- 跑 ----

    def process_key(self, key: str) -> ProcessingResult:
        group = self._groups.get(key)
        if group is None:
            return ProcessingResult(
                False, processor="PBR2DayZ", messages=[self.tr("Group is gone.")]
            )
        return convert_pbr_group(
            group,
            normal_type=self.normal_type.value(),
            resolution=self.resolution.value(),
            make_paa=self.make_paa.isChecked(),
            image_to_paa=self.settings.image_to_paa,
            delete_source=self.delete_source.isChecked(),
            output_suffixes=self.settings.pbr_output_suffixes,
            add_watermark=self.add_watermark.isChecked(),
            watermark_content=self.settings.watermark_content,
            watermark_password=self.settings.watermark_password,
        )

    def apply_result(self, item: Item, result: ProcessingResult) -> None:
        if not result.success:
            item.status = FAILED if result.error else SKIPPED
            item.status_note = result.error or (
                result.messages[-1] if result.messages else ""
            )
            return
        item.status = DONE
        item.status_note = ""
        # 跑过的行留着当记录，但不能再被“开始”跑一遍（源图可能已经被删了）
        item.checked = False
        produced = {self._output_type(path): path for path in result.outputs}
        item.outputs = [
            Slot(
                label=self.tr(OUTPUT_LABELS[out]),
                path=produced.get(out),
                size_text=self.size_text(produced[out]) if out in produced else "",
                missing=out not in produced,
            )
            for out in OUTPUT_TYPES
        ]
        if result.outputs:
            item.size_bottom = human_size(
                sum(self._file_size(path) for path in result.outputs)
            )

    def _output_type(self, path: Path) -> str:
        suffixes = self.settings.pbr_output_suffixes
        for out in OUTPUT_TYPES:
            suffix = suffixes.get(out, "")
            if suffix and path.stem.endswith(suffix):
                return out
        return ""

    # ---- 语言 ----

    def retranslate(self) -> None:
        super().retranslate()
        self.title_label.setText(self.tr("PBR2DayZ"))
        self.status.set_action_text(self.tr("Start"))
        self._normal_box.label.setText(self.tr("Normal"))
        self._resolution_box.label.setText(self.tr("Resolution"))
        self.make_paa.set_label(self.tr("PAA"))
        self.add_watermark.set_label(self.tr("Watermark"))
        self.delete_source.set_label(self.tr("Delete src"))
        self.custom_prefix.setPlaceholderText(self.tr("Custom prefix"))
        self.prefix_mode.set_items(
            [(value, self.tr(label)) for value, label in PREFIX_MODES]
        )
        self.match.set_labels([self.tr("Exact"), self.tr("Fuzzy")])
        self.resolution.set_items(
            [
                (value, value if value != "auto" else self.tr("Auto"))
                for value in RESOLUTIONS
            ]
        )
        self.set_empty_text(
            self.tr("Drop PBR texture sets here"),
            self.tr("Files in the same folder that share a prefix become one group."),
            "basecolor · normal · roughness · metallic · ao",
        )
        self.refresh()
