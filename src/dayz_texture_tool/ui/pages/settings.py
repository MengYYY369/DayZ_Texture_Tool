"""设置页：配一次能用很久的东西。整页自动保存，没有保存按钮。"""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...processors.rvmat import RVMAT_VARIANTS
from .. import paa
from ..theme import PAGE_PAD
from ..widgets.toolbar import Combo, Field, Segmented, button
from .base import BasePage
from .file_page import parse_suffix_text, suffix_error
from .game import MODES as GAME_MODES
from .pbr import OUTPUT_TYPES, PBR_TYPES

MATCH_W = 150
MODE_W = 300
SLOT_W = 110


def flex(field: Field, min_width: int = 120) -> Field:
    field.setMinimumWidth(min_width)
    field.setMaximumWidth(16777215)
    return field


class SettingsPage(BasePage):
    page_key = "settings"

    def __init__(self, settings, parent: QWidget | None = None) -> None:
        super().__init__(self.tr("Settings"), "", parent)
        self.settings = settings

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setObjectName("SettingsScroll")

        inner = QWidget()
        inner.setObjectName("Inner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(PAGE_PAD, 0, PAGE_PAD, 28)
        lay.setSpacing(0)
        self._scroll = scroll

        self._build_general(lay)
        self._build_game(lay)
        self._build_pbr(lay)
        self._build_rvmat(lay)
        lay.addStretch(1)

        scroll.setWidget(inner)
        self.set_body(scroll)
        self.status.set_status(self.tr("Settings are saved automatically."))

    def _rebuild(self) -> None:
        """切语言时整页重搭 —— 这张表行数多，逐个改文字不划算。"""
        inner = QWidget()
        inner.setObjectName("Inner")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(PAGE_PAD, 0, PAGE_PAD, 28)
        lay.setSpacing(0)
        self._build_general(lay)
        self._build_game(lay)
        self._build_pbr(lay)
        self._build_rvmat(lay)
        lay.addStretch(1)
        self._scroll.setWidget(inner)

    # ------------------------------------------------------------ 骨架

    def _section(self, lay: QVBoxLayout, title: str, hint: str = "") -> QVBoxLayout:
        head = QLabel(title)
        head.setObjectName("SectionTitle")
        lay.addSpacing(18)
        lay.addWidget(head)
        if hint:
            note = QLabel(hint)
            note.setObjectName("Hint")
            note.setWordWrap(True)
            lay.addWidget(note)
        lay.addSpacing(10)

        card = QWidget()
        card.setObjectName("Card")
        card_lay = QVBoxLayout(card)
        card_lay.setContentsMargins(0, 0, 0, 0)
        card_lay.setSpacing(0)
        lay.addWidget(card)
        return card_lay

    def _row(self, card_lay: QVBoxLayout, height: int = 56, first: bool = False) -> QHBoxLayout:
        row = QWidget()
        row.setObjectName("CardRow" if not first else "CardRowFirst")
        row.setFixedHeight(height)
        row_lay = QHBoxLayout(row)
        row_lay.setContentsMargins(16, 8, 16, 8)
        row_lay.setSpacing(16)
        card_lay.addWidget(row)
        return row_lay

    def _label(self, text: str, width: int = 0, obj: str = "Small") -> QLabel:
        label = QLabel(text)
        label.setObjectName(obj)
        if width:
            label.setFixedWidth(width)
        return label

    def _cell(self, caption: str, field: Field) -> QWidget:
        """“小标签 + 输入框”一竖格。

        右边那一列有标签，左边那列没有，输入框就会错开一格高度 —— 所以左边也走同一个格子，
        只是标签写个空格占位。
        """
        cell = QWidget()
        cell_lay = QVBoxLayout(cell)
        cell_lay.setContentsMargins(0, 0, 0, 0)
        cell_lay.setSpacing(2)
        cell_lay.addWidget(self._label(caption or " ", 0, "MicroMuted"))
        cell_lay.addWidget(field)
        return cell

    # ------------------------------------------------------------ 通用

    def _build_general(self, lay: QVBoxLayout) -> None:
        card = self._section(lay, self.tr("General"))

        row = self._row(card, first=True)
        row.addWidget(self._label(self.tr("Interface language"), MODE_W))
        self.language = Combo([("zh", "中文"), ("en", "English")], 160)
        self.language.set_value(self.settings.language, notify=False)
        self.language.changed.connect(self._on_language)
        row.addWidget(self.language)
        row.addStretch(1)

        row = self._row(card)
        row.addWidget(self._label(self.tr("Theme"), MODE_W))
        self.theme = Segmented(
            [("dark", self.tr("Dark")), ("light", self.tr("Light"))],
            active=0 if self.settings.theme == "dark" else 1,
            width=160,
        )
        self.theme.changed.connect(self._on_theme)
        row.addWidget(self.theme)
        row.addStretch(1)

        row = self._row(card)
        row.addWidget(self._label(self.tr("ImageToPAA path"), MODE_W))
        self.paa_path = flex(Field(self.settings.image_to_paa), 200)
        self.paa_path.editingFinished.connect(self._on_paa_path)
        row.addWidget(self.paa_path, 1)
        browse = button(self.tr("Browse…"))
        browse.clicked.connect(self._browse_paa)
        row.addWidget(browse)

    # ------------------------------------------------------------ Game2PBR

    def _build_game(self, lay: QVBoxLayout) -> None:
        card = self._section(
            lay,
            self.tr("Game2PBR · output suffixes"),
            self.tr("What each output slot is called."),
        )

        head = self._row(card, height=34, first=True)
        head.addWidget(self._label(self.tr("Mode"), MODE_W, "MicroMuted"))
        head.addWidget(self._label(self.tr("Output suffixes"), 0, "MicroMuted"))
        head.addStretch(1)

        self._slot_labels = {
            "metal": self.tr("Metal"),
            "roughness": self.tr("Rough"),
            "normal": self.tr("Normal"),
            "ao": self.tr("AO"),
            "rgb": self.tr("RGB"),
            "alpha": self.tr("Alpha"),
            "r": self.tr("R"),
            "g": self.tr("G"),
            "b": self.tr("B"),
            "a": self.tr("A"),
            "merged": self.tr("Merged"),
            "converted": self.tr("Converted"),
            "inverted": self.tr("Inverted"),
        }

        for processor, label, slots in GAME_MODES:
            row = self._row(card, height=64)
            row.addWidget(self._label(QCoreApplication.translate("GamePage", label), MODE_W))

            outputs = self.settings.game_output_suffixes.get(processor, {})
            for slot in slots:
                field = Field(outputs.get(slot, ""), SLOT_W)
                field.editingFinished.connect(self._make_output_handler(processor, slot, field))
                row.addWidget(self._cell(self._slot_labels.get(slot, slot), field), 0, Qt.AlignVCenter)
            row.addStretch(1)

    # ------------------------------------------------------------ PBR2DayZ

    def _build_pbr(self, lay: QVBoxLayout) -> None:
        card = self._section(
            lay,
            self.tr("PBR2DayZ · group keywords and output suffixes"),
            self.tr("Used to tell which PBR slot a file belongs to."),
        )

        self._type_labels = {
            "basecolor": self.tr("Base color"),
            "normal": self.tr("Normal"),
            "roughness": self.tr("Roughness"),
            "metallic": self.tr("Metallic"),
            "ao": self.tr("AO"),
        }
        self._out_labels = {
            "co": self.tr("Color"),
            "nohq": self.tr("Normal"),
            "smdi": self.tr("Specular"),
            "as": self.tr("Ambient"),
        }

        for index, tex_type in enumerate(PBR_TYPES):
            row = self._row(card, first=index == 0)
            row.addWidget(self._label(self._type_labels[tex_type], MATCH_W))
            field = flex(Field(", ".join(self.settings.pbr_suffixes.get(tex_type, [])), 200), 200)
            field.editingFinished.connect(self._make_keyword_handler(tex_type, field))
            row.addWidget(field, 1)

        row = self._row(card, height=64)
        row.addWidget(self._label(self.tr("Output suffixes"), MATCH_W))
        for out in OUTPUT_TYPES:
            field = Field(self.settings.pbr_output_suffixes.get(out, ""), SLOT_W)
            field.editingFinished.connect(self._make_pbr_output_handler(out, field))
            row.addWidget(self._cell(self._out_labels[out], field))
        row.addStretch(1)

    # ------------------------------------------------------------ RVMAT

    def _build_rvmat(self, lay: QVBoxLayout) -> None:
        card = self._section(
            lay,
            self.tr("RVMAT"),
            self.tr("Every generated variant points class Stage3 at one of these textures."),
        )

        for index, suffix in enumerate(RVMAT_VARIANTS):
            row = self._row(card, first=index == 0)
            row.addWidget(self._label(suffix, MATCH_W))
            field = flex(Field(self.settings.rvmat_damage_textures.get(suffix, ""), 200), 200)
            field.editingFinished.connect(self._make_damage_texture_handler(suffix, field))
            row.addWidget(field, 1)

        row = self._row(card)
        row.addWidget(self._label(self.tr("Skip suffixes"), MATCH_W))
        field = flex(Field(", ".join(self.settings.rvmat_excluded_suffixes), 200), 200)
        field.editingFinished.connect(self._make_excluded_handler(field))
        row.addWidget(field, 1)

    # ------------------------------------------------------------ 保存

    def _save(self) -> None:
        window = self.window()
        if hasattr(window, "save_settings"):
            window.save_settings()

    def _on_language(self, value: str) -> None:
        self.settings.language = value
        self._save()
        window = self.window()
        if hasattr(window, "apply_language"):
            window.apply_language()

    def _on_theme(self, value: str) -> None:
        self.settings.theme = value
        self._save()
        window = self.window()
        if hasattr(window, "apply_theme"):
            window.apply_theme()

    def _on_paa_path(self) -> None:
        self.settings.image_to_paa = self.paa_path.text().strip()
        paa.set_tool(self.settings.image_to_paa)
        self._save()

    def _browse_paa(self) -> None:
        name, _ = QFileDialog.getOpenFileName(
            self, self.tr("ImageToPAA path"), self.paa_path.text(), "ImageToPAA (ImageToPAA.exe)"
        )
        if name:
            self.paa_path.setText(name)
            self._on_paa_path()

    def _make_output_handler(self, processor: str, slot: str, field: Field):
        def handler() -> None:
            table = self.settings.game_output_suffixes.setdefault(processor, {})
            table[slot] = field.text().strip()
            error = suffix_error([value for value in table.values() if value])
            field.set_invalid(bool(error))
            if error:
                self.status.set_status(QCoreApplication.translate("FilePage", error))
                return
            self._save()
            self.status.set_status(self.tr("Settings are saved automatically."))

        return handler

    def _make_keyword_handler(self, tex_type: str, field: Field):
        def handler() -> None:
            self.settings.pbr_suffixes[tex_type] = parse_suffix_text(field.text())
            self._save()

        return handler

    def _make_pbr_output_handler(self, out: str, field: Field):
        def handler() -> None:
            self.settings.pbr_output_suffixes[out] = field.text().strip()
            self._save()

        return handler

    def _make_damage_texture_handler(self, suffix: str, field: Field):
        def handler() -> None:
            self.settings.rvmat_damage_textures[suffix] = field.text().strip()
            self._save()

        return handler

    def _make_excluded_handler(self, field: Field):
        def handler() -> None:
            self.settings.rvmat_excluded_suffixes = parse_suffix_text(field.text())
            self._save()

        return handler

    # ------------------------------------------------------------ 语言

    def retranslate(self) -> None:
        self.title_label.setText(self.tr("Settings"))
        self.status.set_status(self.tr("Settings are saved automatically."))
        self._rebuild()
