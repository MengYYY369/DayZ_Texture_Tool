"""RVMAT：一份材质复制出三份损坏变体。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP, QUrl
from PySide6.QtGui import QDesktopServices

from ...models import ProcessingResult
from ...processors.rvmat import (
    RVMAT_VARIANTS,
    collect_rvmat_files,
    convert_rvmat,
    excluded_variant,
)
from ..items import PENDING, SKIPPED, Item, Slot
from ..widgets.toolbar import Toggle
from .file_page import FilePage


class RvmatPage(FilePage):
    page_key = "rvmat"

    def __init__(self, settings, parent=None) -> None:
        super().__init__(
            settings,
            title="RVMAT",
            action_text="Start",
            in_width=70,
            in_label=QT_TRANSLATE_NOOP("FilePage", "Source"),
            out_label=QT_TRANSLATE_NOOP("FilePage", "Variants"),
            empty_title="Drop .rvmat materials here",
            empty_hint="Each material gets a _worn, _damage and _destruct copy.",
            empty_accept="RVMAT",
            parent=parent,
        )

        self.toggles: dict[str, Toggle] = {}
        for suffix in RVMAT_VARIANTS:
            toggle = Toggle(suffix, on=True)
            toggle.toggled.connect(self._on_variants)
            self.toggles[suffix] = toggle
            self.add_toolbar(toggle)
        self.add_toolbar_actions()

        self.set_empty_text(
            self.tr("Drop .rvmat materials here"),
            self.tr("Each material gets a _worn, _damage and _destruct copy."),
            "RVMAT",
        )

    # ---- 工具条 ----

    def variants(self) -> list[str]:
        """当前勾着的变体，顺序固定按引擎那三个来。"""
        return [suffix for suffix in RVMAT_VARIANTS if self.toggles[suffix].isChecked()]

    def _on_variants(self) -> None:
        """勾选框变了，还没跑过的行把右边的空槽重摆一遍。"""
        for item in self.list.items():
            if item.status in (PENDING, SKIPPED) and item.selectable:
                item.outputs = self._empty_slots()
        self.list.view.viewport().update()
        self.refresh()

    def _empty_slots(self) -> list[Slot]:
        """三个格子永远都在，不管勾了几个。

        没勾的那格是空槽（placeholder 留空 → 画 "—"），让人一眼看出这一份不会
        被生成 —— 而不是让格子凭空消失、剩下两格重新排版。Q6 说的是「每行三个
        结果格」，不是「每行 N 个」。

        label 留空：它是画在格子**下方**的那行小字，也就是产物文件名。还没跑
        之前没有产物，那行就该是空的 —— 格子里的大字（placeholder）已经说清楚
        这一格会生成哪个变体了，不必再写一遍。
        """
        chosen = self.variants()
        return [
            Slot(label="", missing=True, placeholder=suffix if suffix in chosen else "")
            for suffix in RVMAT_VARIANTS
        ]

    def mode_text(self) -> str:
        return self.tr("Variants: {list}").format(list=" ".join(self.variants()) or "—")

    def file_filter(self) -> str:
        return self.tr("RVMAT") + " (*.rvmat)"

    # ---- 行 ----

    def build_items(self, paths: list[Path]) -> list[Item]:
        items = []
        for path in paths:
            for found in collect_rvmat_files(path):
                items.append(self._make_item(found))
        return items

    def _make_item(self, path: Path) -> Item:
        item = Item(key=str(path), title=path.name, subtitle=path.parent.name)
        item.size_bottom = self.size_text(path)
        item.inputs = [Slot(label=path.name, path=path, size_text=item.size_bottom)]
        hit = excluded_variant(path, self.settings.rvmat_excluded_suffixes)
        if hit:
            # 已经是变体了，不当输入；列出来是为了让人看见"为什么这行没跑"。
            item.status = SKIPPED
            item.status_note = self.tr("Already a {suffix} variant.").format(suffix=hit)
            item.selectable = False
            item.checked = False
            item.outputs = []
        else:
            item.status = PENDING
            item.outputs = self._empty_slots()
        return item

    @staticmethod
    def _suffix_of(path: Path) -> str:
        stem = path.stem.lower()
        for suffix in RVMAT_VARIANTS:
            if stem.endswith(suffix.lower()):
                return suffix
        return ""

    # ---- 跑 ----

    def process_key(self, key: str) -> ProcessingResult:
        return convert_rvmat(key, self.variants(), self.settings.rvmat_damage_textures)

    def apply_result(self, item: Item, result: ProcessingResult) -> None:
        super().apply_result(item, result)
        if not result.success:
            return
        # 按后缀把产物认回来，而不是直接拿 result.outputs 铺 —— 这样格子永远是三个、
        # 顺序永远一样，跑之前跑之后长一个样。没生成的（没勾的、或那一个失败的）
        # 留空槽。
        made = {self._suffix_of(path): path for path in result.outputs}
        slots: list[Slot] = []
        for suffix in RVMAT_VARIANTS:
            path = made.get(suffix)
            if path is None:
                # 没生成的那格和跑之前长得一模一样：空格子，下方也不写文件名。
                slots.append(Slot(label="", missing=True, placeholder=""))
            else:
                # 大字是变体后缀，下面小字是产物文件名。不塞 size_text：行右边
                # 已经有一列尺寸了，70px 的格子里放不下第三行。
                slots.append(Slot(label=path.stem, path=path, placeholder=suffix))
        item.outputs = slots

    # ---- 点格子 ----

    def open_preview(self, item: Item, index: int) -> None:
        """rvmat 是文本，用系统默认程序打开比弹一个读不出图的窗口有用。"""
        slot = dict(self.preview_slots(item)).get(index)
        if slot is not None and slot.path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(slot.path)))

    # ---- 语言 ----

    def retranslate(self) -> None:
        super().retranslate()
        self.title_label.setText(self.tr("RVMAT"))
        self.status.set_action_text(self.tr("Start"))
        self.set_empty_text(
            self.tr("Drop .rvmat materials here"),
            self.tr("Each material gets a _worn, _damage and _destruct copy."),
            "RVMAT",
        )
        self.refresh()
