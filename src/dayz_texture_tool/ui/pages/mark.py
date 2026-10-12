"""水印：嵌入和检测。水印图肉眼跟原图一模一样，所以右边那栏显示的是文字结果。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QT_TRANSLATE_NOOP

from ...models import ProcessingResult
from ...processors.watermark import add_watermark, detect_watermark
from ..items import DONE, FAILED, SKIPPED, Item, Slot
from ..widgets.toolbar import Field, Segmented, Toggle, labelled
from .file_page import FilePage

EMPTY_NOTE = "—"


class MarkPage(FilePage):
    page_key = "mark"

    def __init__(self, settings, parent=None) -> None:
        super().__init__(
            settings,
            title="Watermark",
            action_text="Start",
            in_width=70,
            in_label=QT_TRANSLATE_NOOP("FilePage", "Source"),
            out_label=QT_TRANSLATE_NOOP("FilePage", "Result"),
            empty_title="Drop images here",
            empty_hint="A watermark is invisible, so the result column reports what happened.",
            empty_accept="PNG · TGA · TIF · JPG · BMP · DDS · PAA",
            parent=parent,
        )

        self.mode = Segmented(
            [("embed", self.tr("Embed")), ("detect", self.tr("Detect"))],
            active=0,
            width=140,
        )
        self.mode.changed.connect(self._on_mode)

        self.content = Field(settings.watermark_content, 150)
        self.content.setPlaceholderText(self.tr("Watermark text"))
        self.content.editingFinished.connect(self._on_content)

        self.password = Field(str(settings.watermark_password), 60)
        self.password.editingFinished.connect(self._on_password)

        self.length = Field(str(settings.watermark_length), 60)
        self.length.editingFinished.connect(self._on_length)

        self.overwrite = Toggle(self.tr("Overwrite"))

        self._content_box = labelled(self.tr("Content"), self.content)
        self._password_box = labelled(self.tr("Password"), self.password)
        self._length_box = labelled(self.tr("Length"), self.length)

        self.add_toolbar(
            self.mode,
            self._content_box,
            self._password_box,
            self._length_box,
            self.overwrite,
        )
        self.add_toolbar_actions()

        self.set_empty_text(
            self.tr("Drop images here"),
            self.tr(
                "A watermark is invisible, so the result column reports what happened."
            ),
            "PNG · TGA · TIF · JPG · BMP · DDS · PAA",
        )
        self._sync_fields()

    # ---- 工具条 ----

    def detecting(self) -> bool:
        return self.mode.value() == "detect"

    def _sync_fields(self) -> None:
        """检测必须有长度，嵌入的长度是跑出来的结果，所以两边各灰一组。"""
        detecting = self.detecting()
        self.content.setEnabled(not detecting)
        self.overwrite.setEnabled(not detecting)
        self.length.setEnabled(detecting)
        self._dim(self._content_box, detecting)
        self._dim(self._length_box, not detecting)

    def _dim(self, box, dim: bool) -> None:
        box.label.setObjectName("SmallMuted" if dim else "SmallDim")
        box.label.style().unpolish(box.label)
        box.label.style().polish(box.label)

    def _on_mode(self, value: str) -> None:
        self._sync_fields()

    def _on_content(self) -> None:
        self.settings.watermark_content = self.content.text()
        self._save_settings()

    def _on_password(self) -> None:
        self.settings.watermark_password = self.password.text()
        self._save_settings()

    def _on_length(self) -> None:
        try:
            self.settings.watermark_length = int(self.length.text().strip() or "0")
        except ValueError:
            self.settings.watermark_length = 0
        self._save_settings()

    def _remember_length(self, length: int) -> None:
        self.settings.watermark_length = length
        self.length.setText(str(length))
        self._save_settings()

    def mode_text(self) -> str:
        if self.detecting():
            return self.tr("Detect · password {password} · length {length}").format(
                password=self.settings.watermark_password,
                length=self.settings.watermark_length,
            )
        return self.tr("Embed · {count} character(s)").format(
            count=len(self.settings.watermark_content)
        )

    # ---- 行 ----

    def build_items(self, paths: list[Path]) -> list[Item]:
        items = []
        for path in paths:
            if not path.is_file():
                continue
            item = Item(
                key=str(path),
                title=path.name,
                subtitle=path.parent.name,
                inputs=[
                    Slot(label=path.name, path=path, size_text=self.size_text(path))
                ],
                output_note=EMPTY_NOTE,
                size_top=self.image_size_text(path),
                size_bottom=self.size_text(path),
            )
            items.append(item)
        return items

    # ---- 跑 ----

    def start(self) -> None:
        for item in self.list.checked_items():
            item.output_note = self.tr("Working…")
        super().start()

    def process_key(self, key: str) -> ProcessingResult:
        if self.detecting():
            return detect_watermark(
                key,
                self.settings.watermark_password,
                self.settings.watermark_length,
                image_to_paa=self.settings.image_to_paa,
            )
        return add_watermark(
            key,
            self.settings.watermark_content,
            self.settings.watermark_password,
            image_to_paa=self.settings.image_to_paa,
            overwrite=self.overwrite.isChecked(),
        )

    def apply_result(self, item: Item, result: ProcessingResult) -> None:
        if not result.success:
            item.status = FAILED if result.error else SKIPPED
            item.status_note = result.error or (
                result.messages[-1] if result.messages else ""
            )
            item.output_note = EMPTY_NOTE
            return
        item.status = DONE
        item.status_note = ""
        if self.detecting():
            text = str(result.metadata.get("watermark_text") or "")
            item.output_note = (
                self.tr("Detected: {text}").format(text=text)
                if text
                else self.tr("No watermark found")
            )
        else:
            item.output_note = self.tr("Watermark embedded")
            length = result.metadata.get("watermark_length")
            if length:
                self._remember_length(int(length))

    # ---- 语言 ----

    def retranslate(self) -> None:
        super().retranslate()
        self.title_label.setText(self.tr("Watermark"))
        self.status.set_action_text(self.tr("Start"))
        self.mode.set_labels([self.tr("Embed"), self.tr("Detect")])
        self._content_box.label.setText(self.tr("Content"))
        self._password_box.label.setText(self.tr("Password"))
        self._length_box.label.setText(self.tr("Length"))
        self.content.setPlaceholderText(self.tr("Watermark text"))
        self.overwrite.set_label(self.tr("Overwrite"))
        self.set_empty_text(
            self.tr("Drop images here"),
            self.tr(
                "A watermark is invisible, so the result column reports what happened."
            ),
            "PNG · TGA · TIF · JPG · BMP · DDS · PAA",
        )
        self.refresh()
