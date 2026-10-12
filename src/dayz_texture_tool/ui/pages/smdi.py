"""SMDI：一张颜色贴图换一张高光贴图。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP

from ...models import ProcessingResult
from ...processors.smdi import convert_color_to_smdi, parse_specular_power
from ..items import Item, Slot
from ..widgets.toolbar import Field, Toggle, labelled
from .file_page import FilePage


class SmdiPage(FilePage):
    page_key = "smdi"

    def __init__(self, settings, parent=None) -> None:
        super().__init__(
            settings,
            title="SMDI",
            action_text="Start",
            in_width=70,
            in_label=QT_TRANSLATE_NOOP("FilePage", "Source"),
            out_label=QT_TRANSLATE_NOOP("FilePage", "Output"),
            empty_title="Drop color textures here",
            empty_hint="Each image turns into one SMDI specular map.",
            empty_accept="PNG · TGA · TIF · JPG · BMP · DDS",
            parent=parent,
        )

        self.power = Field(f"{settings.smdi_specular_power:g}", 72)
        self.power.editingFinished.connect(self._on_power)
        self.make_paa = Toggle(self.tr("PAA"), on=True)
        self._power_box = labelled(self.tr("Specular"), self.power)

        self.add_toolbar(self._power_box, self.make_paa)
        self.add_toolbar_actions()

        self.set_empty_text(
            self.tr("Drop color textures here"),
            self.tr("Each image turns into one SMDI specular map."),
            "PNG · TGA · TIF · JPG · BMP · DDS",
        )

    # ---- 工具条 ----

    def _on_power(self) -> None:
        self.settings.smdi_specular_power = parse_specular_power(self.power.text())
        self.power.setText(f"{self.settings.smdi_specular_power:g}")
        self._save_settings()
        self.refresh()

    def mode_text(self) -> str:
        return self.tr("Specular power {power:g}").format(
            power=self.settings.smdi_specular_power
        )

    # ---- 行 ----

    def build_items(self, paths: list[Path]) -> list[Item]:
        items = []
        for path in paths:
            if not path.is_file():
                continue
            items.append(
                Item(
                    key=str(path),
                    title=path.name,
                    subtitle=path.parent.name,
                    inputs=[
                        Slot(label=path.name, path=path, size_text=self.size_text(path))
                    ],
                    size_top=self.image_size_text(path),
                    size_bottom=self.size_text(path),
                )
            )
        return items

    # ---- 跑 ----

    def process_key(self, key: str) -> ProcessingResult:
        return convert_color_to_smdi(
            key,
            self.settings.smdi_specular_power,
            self.make_paa.isChecked(),
            image_to_paa=self.settings.image_to_paa,
        )

    # ---- 语言 ----

    def retranslate(self) -> None:
        super().retranslate()
        self.title_label.setText(self.tr("SMDI"))
        self.status.set_action_text(self.tr("Start"))
        self._power_box.label.setText(self.tr("Specular"))
        self.make_paa.set_label(self.tr("PAA"))
        self.set_empty_text(
            self.tr("Drop color textures here"),
            self.tr("Each image turns into one SMDI specular map."),
            "PNG · TGA · TIF · JPG · BMP · DDS",
        )
        self.refresh()
