"""界面层的测试。跑的时候用离屏平台，不开真窗口。

    QT_QPA_PLATFORM=offscreen python -m unittest tests.test_ui_pages
"""

from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QDropEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from dayz_texture_tool.models import ProcessingResult  # noqa: E402
from dayz_texture_tool.settings import AppSettings  # noqa: E402
from dayz_texture_tool.ui import theme  # noqa: E402
from dayz_texture_tool.ui.items import DONE, FAILED, SKIPPED  # noqa: E402
from dayz_texture_tool.ui.shell import MainWindow  # noqa: E402

_app: QApplication | None = None


def setUpModule() -> None:  # noqa: N802
    global _app
    _app = QApplication.instance() or QApplication([])
    theme.apply(_app, "dark")


def pump(seconds: float = 0.02) -> None:
    """转一下事件循环，让后台线程的结果回到主线程。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        QApplication.processEvents()
        time.sleep(0.001)


def wait_for(page, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if page.status.action is None or page.status.action.isEnabled():
            return
        time.sleep(0.005)
    raise AssertionError("处理没在预期时间内结束")


def drop_event(paths: list[Path]) -> QDropEvent:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    event = QDropEvent(QPointF(12, 12), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    event._mime = mime  # 事件不持有 QMimeData，不抱着就会被回收掉
    return event


def make_image(path: Path, size: int = 32) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (size, size), (120, 80, 200, 255)).save(path)
    return path


class WindowCase(unittest.TestCase):
    """每个用例一个新窗口，不碰真的设置文件和会话文件。"""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.settings = AppSettings()
        self.settings.language = "en"
        self._patches = [
            patch("dayz_texture_tool.ui.shell.save_settings"),
            patch("dayz_texture_tool.ui.session.save"),
            patch("dayz_texture_tool.ui.session.load", return_value={}),
            patch("dayz_texture_tool.ui.session.clear"),
        ]
        for item in self._patches:
            item.start()
            self.addCleanup(item.stop)
        self.win = MainWindow(self.settings)
        self.win.resize(1440, 900)
        self.addCleanup(self.win.deleteLater)
        self.addCleanup(self._drop_translator)

    def _drop_translator(self) -> None:
        # 翻译器是装在 QApplication 上的，不拆下来会泄给下一个用例
        QApplication.instance().removeTranslator(self.win._translator)

    def page(self, key: str):
        self.win.show_page(key)
        pump()
        return self.win.pages[key]


class DropTests(WindowCase):
    def test_dropping_files_adds_rows(self) -> None:
        page = self.page("game")
        files = [make_image(self.root / "a_nrm.png"), make_image(self.root / "b_nrm.png")]
        page.dropEvent(drop_event(files))
        self.assertEqual(len(page.list.items()), 2)
        self.assertEqual(page.list.items()[0].title, "a_nrm.png")

    def test_dropping_a_folder_expands_it(self) -> None:
        folder = self.root / "set"
        make_image(folder / "x_nrm.png")
        make_image(folder / "y_nrm.png")
        page = self.page("game")
        page.dropEvent(drop_event([folder]))
        self.assertEqual(len(page.list.items()), 2)

    def test_same_file_twice_only_counts_once(self) -> None:
        page = self.page("game")
        path = make_image(self.root / "a_nrm.png")
        page.add_paths([path])
        page.add_paths([path])
        self.assertEqual(len(page.list.items()), 1)

    def test_matching_suffix_decides_selectable(self) -> None:
        page = self.page("game")
        page.add_paths(
            [
                make_image(self.root / "good_nrm.png"),
                make_image(self.root / "other_mra.png"),
            ]
        )
        by_name = {item.title: item for item in page.list.items()}
        self.assertTrue(by_name["good_nrm.png"].selectable)
        self.assertEqual(by_name["good_nrm.png"].status, "pending")
        self.assertFalse(by_name["other_mra.png"].selectable)
        self.assertEqual(by_name["other_mra.png"].status, SKIPPED)


class ModeTests(WindowCase):
    def test_switching_mode_changes_match_suffix(self) -> None:
        page = self.page("game")
        self.assertEqual(page.mode()[0], "DF_NRM")
        self.assertEqual(page.match_suffixes(), ["_nrm"])
        page.mode_combo.set_value("DF_MRA")
        pump()
        self.assertEqual(page.match_suffixes(), ["_mra"])
        self.assertEqual(self.settings.game_suffixes["DF_MRA"], ["_mra"])

    def test_switching_mode_reclassifies_rows(self) -> None:
        page = self.page("game")
        page.add_paths([make_image(self.root / "thing_mra.png")])
        self.assertEqual(page.list.items()[0].status, SKIPPED)
        page.mode_combo.set_value("DF_MRA")
        pump()
        self.assertEqual(page.list.items()[0].status, "pending")

    def test_output_slots_follow_the_mode(self) -> None:
        page = self.page("game")
        page.mode_combo.set_value("SplitRGBAProcessor")
        pump()
        page.add_paths([make_image(self.root / "c_rgba.png")])
        labels = [slot.label for slot in page.list.items()[0].outputs]
        self.assertEqual(labels, ["R", "G", "B", "A"])


class RunTests(WindowCase):
    def test_start_calls_the_processor_with_the_right_arguments(self) -> None:
        page = self.page("game")
        page.add_paths([make_image(self.root / "wall_nrm.png")])
        page.delete_source.setChecked(True)
        calls: list[tuple] = []

        def fake(path, processor, **kwargs):
            calls.append((path, processor, kwargs))
            return ProcessingResult(True, input_path=Path(path), processor=processor)

        with patch("dayz_texture_tool.ui.pages.game.process_game2pbr", side_effect=fake):
            page.start()
            wait_for(page)

        self.assertEqual(len(calls), 1)
        path, processor, kwargs = calls[0]
        self.assertEqual(Path(path).name, "wall_nrm.png")
        self.assertEqual(processor, "DF_NRM")
        self.assertTrue(kwargs["delete_source"])
        self.assertEqual(kwargs["output_suffixes"], self.settings.game_output_suffixes["DF_NRM"])

    def test_skipped_and_failed_are_counted_separately(self) -> None:
        page = self.page("game")
        page.add_paths(
            [
                make_image(self.root / "ok_nrm.png"),
                make_image(self.root / "nope_nrm.png"),
            ]
        )
        items = page.list.items()
        page.apply_result(items[0], ProcessingResult(True, processor="DF_NRM"))
        page.apply_result(
            items[1],
            ProcessingResult(False, processor="DF_NRM", error="boom"),
        )
        page.refresh()
        self.assertEqual(items[0].status, DONE)
        self.assertEqual(items[1].status, FAILED)
        self.assertIn("1 done", page.status._status.text())
        self.assertIn("1 failed", page.status._status.text())
        self.assertIn("0 skipped", page.status._status.text())
        self.assertFalse(page.issues.isHidden())

    def test_unchecked_rows_are_not_processed(self) -> None:
        page = self.page("game")
        page.add_paths(
            [
                make_image(self.root / "one_nrm.png"),
                make_image(self.root / "two_nrm.png"),
            ]
        )
        page.list.items()[1].checked = False
        calls: list[str] = []

        def fake(path, processor, **kwargs):
            calls.append(Path(path).name)
            return ProcessingResult(True, input_path=Path(path), processor=processor)

        with patch("dayz_texture_tool.ui.pages.game.process_game2pbr", side_effect=fake):
            page.start()
            wait_for(page)
        self.assertEqual(calls, ["one_nrm.png"])

    def test_start_does_nothing_without_checked_rows(self) -> None:
        page = self.page("game")
        page.add_paths([make_image(self.root / "one_nrm.png")])
        page.list.items()[0].checked = False
        with patch("dayz_texture_tool.ui.pages.game.process_game2pbr") as fake:
            page.start()
            pump()
        fake.assert_not_called()


class PbrTests(WindowCase):
    def _fixture(self) -> Path:
        folder = self.root / "brick"
        for kind in ("basecolor", "normal", "roughness", "metallic", "ao"):
            make_image(folder / f"brick_{kind}.png")
        return folder

    def test_one_folder_becomes_one_group(self) -> None:
        page = self.page("pbr")
        page.add_paths([self._fixture()])
        self.assertEqual(len(page.list.items()), 1)
        item = page.list.items()[0]
        self.assertEqual(item.title, "brick")
        self.assertEqual(len(item.inputs), 5)
        self.assertEqual(len(item.outputs), 4)

    def test_missing_types_leave_empty_slots(self) -> None:
        folder = self.root / "stone"
        for kind in ("basecolor", "normal", "roughness"):
            make_image(folder / f"stone_{kind}.png")
        page = self.page("pbr")
        page.add_paths([folder])
        item = page.list.items()[0]
        missing = [slot.label for slot in item.inputs if slot.missing]
        self.assertEqual(missing, ["Metallic", "AO"])

    def test_group_without_convertible_textures_is_skipped(self) -> None:
        folder = self.root / "odd"
        make_image(folder / "odd_metallic.png")  # 四张输出没有一张用得上金属度
        page = self.page("pbr")
        page.add_paths([folder])
        item = page.list.items()[0]
        self.assertEqual(item.status, SKIPPED)
        self.assertFalse(item.selectable)

    def test_outputs_land_in_their_own_slot(self) -> None:
        page = self.page("pbr")
        page.add_paths([self._fixture()])
        item = page.list.items()[0]
        page.apply_result(
            item,
            ProcessingResult(
                True,
                processor="PBR2DayZ",
                outputs=[
                    self.root / "brick_co.tga",
                    self.root / "brick_nohq.tga",
                    self.root / "brick_smdi.tga",
                    self.root / "brick_as.tga",
                ],
            ),
        )
        self.assertEqual(item.status, DONE)
        self.assertTrue(all(not slot.missing for slot in item.outputs))


class LanguageTests(WindowCase):
    def test_switching_language_rewrites_the_sidebar(self) -> None:
        self.page("game")
        self.assertEqual(self.win.sidebar._items["settings"].text(), "Settings")
        self.win.toggle_language()
        pump()
        self.assertEqual(self.win.sidebar._items["settings"].text(), "设置")
        self.assertEqual(self.win.pages["game"].title_label.text(), "Game2PBR")
        self.assertEqual(self.win.pages["game"].status.action.text(), "开始处理")

    def test_settings_page_survives_a_language_switch(self) -> None:
        page = self.page("settings")
        before = len(page.findChildren(type(page.title_label)))
        self.win.toggle_language()
        pump()
        self.assertGreater(len(page.findChildren(type(page.title_label))), 0)
        self.assertGreater(before, 0)

    def test_missing_translation_falls_back_to_english(self) -> None:
        # 默认语言是英文，漏翻只会退回英文，不会变成看不懂的东西
        self.assertEqual(self.settings.language, "en")


class SessionTests(WindowCase):
    def test_pages_report_their_keys(self) -> None:
        page = self.page("game")
        page.add_paths([make_image(self.root / "a_nrm.png")])
        payload = self.win.pages["game"].to_session()
        self.assertEqual(payload["keys"], [str(self.root / "a_nrm.png")])

    def test_loading_a_session_restores_rows(self) -> None:
        path = make_image(self.root / "a_nrm.png")
        page = self.page("game")
        page.load_session({"keys": [str(path)]})
        self.assertEqual(len(page.list.items()), 1)

    def test_loading_ignores_missing_files(self) -> None:
        page = self.page("game")
        page.load_session({"keys": [str(self.root / "gone_nrm.png")]})
        self.assertEqual(len(page.list.items()), 0)


SAMPLE_RVMAT = (
    'class Stage1\n{\n\ttexture="a_nohq.paa";\n};\n'
    'class Stage3\n{\n\ttexture="#(argb,8,8,3)color(0,0,0,0,MC)";\n};\n'
)


class RvmatPageTests(WindowCase):
    def make_rvmat(self, name="crate.rvmat", text=SAMPLE_RVMAT):
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_dropping_a_material_adds_a_row_with_three_empty_slots(self):  # Q6
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        item = page.list.items()[0]
        self.assertEqual(item.title, "crate.rvmat")
        self.assertEqual([slot.placeholder for slot in item.outputs], ["_worn", "_damage", "_destruct"])
        self.assertTrue(all(slot.missing for slot in item.outputs))

    def test_dropping_a_folder_recurses(self):  # Q12
        root = Path(self.tmp.name) / "mod"
        (root / "sub").mkdir(parents=True)
        (root / "a.rvmat").write_text(SAMPLE_RVMAT, encoding="utf-8")
        (root / "sub" / "b.rvmat").write_text(SAMPLE_RVMAT, encoding="utf-8")
        (root / "sub" / "readme.txt").write_text("x", encoding="utf-8")

        page = self.page("rvmat")
        page.dropEvent(drop_event([root]))
        pump()

        self.assertEqual(sorted(item.title for item in page.list.items()), ["a.rvmat", "b.rvmat"])

    def test_a_variant_file_is_listed_but_marked_skipped(self):  # Q7
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat("crate_worn.rvmat")]))
        pump()
        item = page.list.items()[0]
        self.assertEqual(item.status, SKIPPED)
        self.assertFalse(item.selectable)
        self.assertFalse(item.checked)

    def test_unchecking_a_variant_empties_its_slot_without_removing_it(self):  # Q13, Q6
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.toggles["_destruct"].setChecked(False)
        page._on_variants()
        pump()
        slots = page.list.items()[0].outputs
        # 还是三格 —— 没勾的那格变成空槽，不是整格消失。
        self.assertEqual([slot.placeholder for slot in slots], ["_worn", "_damage", ""])
        # 格子下方那行小字（产物文件名）跑之前是空的。
        self.assertEqual([slot.label for slot in slots], ["", "", ""])
        self.assertTrue(all(slot.missing for slot in slots))

    def test_only_checked_variants_are_written(self):  # Q13
        page = self.page("rvmat")
        page.toggles["_damage"].setChecked(False)
        page.toggles["_destruct"].setChecked(False)
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.start()
        wait_for(page)
        names = sorted(path.name for path in Path(self.tmp.name).glob("crate_*.rvmat"))
        self.assertEqual(names, ["crate_worn.rvmat"])
        # 没勾的两格跑完还是空槽，不是变成两个格。生成了的那格下方写上文件名。
        slots = page.list.items()[0].outputs
        self.assertEqual([slot.placeholder for slot in slots], ["_worn", "", ""])
        self.assertEqual([slot.label for slot in slots], ["crate_worn", "", ""])
        self.assertTrue(slots[1].missing and slots[2].missing)

    def test_result_cells_carry_the_suffix_and_the_file_name(self):  # Q8
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.start()
        wait_for(page)
        slots = page.list.items()[0].outputs
        self.assertEqual([slot.placeholder for slot in slots], ["_worn", "_damage", "_destruct"])
        self.assertEqual([slot.label for slot in slots], ["crate_worn", "crate_damage", "crate_destruct"])
        self.assertTrue(all(slot.path is not None and not slot.missing for slot in slots))

    def test_a_material_without_stage3_lands_in_the_issues_panel(self):  # Q2b
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat("broken.rvmat", 'class Stage1\n{\n\ttexture="a.paa";\n};\n')]))
        pump()
        page.start()
        wait_for(page)
        item = page.list.items()[0]
        self.assertEqual(item.status, FAILED)
        self.assertTrue(item.status_note)
        # 三份候选产物一个都不该落地，不是只看第一份。
        for suffix in ("_worn", "_damage", "_destruct"):
            self.assertFalse((Path(self.tmp.name) / f"broken{suffix}.rvmat").exists())
        # IssuesPanel 不存列表，它直接把内容画成 label —— 只能看标题和可见性。
        # 用 isHidden() 而不是 isVisible()：WindowCase 从来不 win.show()，
        # offscreen 下没显示过的窗口里 isVisible() 恒为 False。现有测试也用 isHidden。
        self.assertFalse(page.issues.isHidden())
        self.assertEqual(page.issues.title.text(), "Issues · 1")

    def test_clicking_a_cell_opens_the_system_default_program(self):  # Q9
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.start()
        wait_for(page)
        with patch("dayz_texture_tool.ui.pages.rvmat.QDesktopServices.openUrl") as opened:
            page._on_slot(page.list.items()[0].key, 1000)
        self.assertTrue(opened.called)
        self.assertIn("crate_worn.rvmat", opened.call_args[0][0].toLocalFile())

    def test_the_page_re_renders_on_a_language_switch(self):
        # 中文那一半要等 Task 7 把 .qm 编出来才能断言 —— 这里只证明切换会重画，
        # 且切回来是干净的英文。完整的中英对照在 Task 7 Step 4。
        page = self.page("rvmat")
        self.assertEqual(page.title_label.text(), "RVMAT")
        self.win.toggle_language()
        pump()
        self.win.toggle_language()
        pump()
        self.assertEqual(page.status.action.text(), "Start")
        self.assertEqual(page.title_label.text(), "RVMAT")


if __name__ == "__main__":
    unittest.main()
