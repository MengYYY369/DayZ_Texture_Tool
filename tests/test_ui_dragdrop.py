import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.ui import main_window


class DummyTk:
    def splitlist(self, value):
        return value.split("|")


class DummyApp(main_window.DayZTextureToolApp):
    def __init__(self):
        self.tk = DummyTk()
        self.game_pending_paths = []
        self.game_selected_paths = set()
        self.pbr_pending_paths = []
        self.pbr_selected_paths = set()
        self.pbr_folder = None
        self.pbr_root_context = None
        self.selected_game_processor = "DF_NRM"
        self.settings = type("Settings", (), {
            "game_match_mode": "exact",
            "game_suffixes": {"DF_NRM": ["_nrm"]},
            "game_output_suffixes": {"DF_NRM": {"normal": "_N"}},
            "pbr_suffixes": {},
            "pbr_match_mode": "fuzzy",
            "pbr_output_suffixes": {},
            "pbr_prefix_mode": "auto",
            "pbr_custom_prefix": "",
            "image_to_paa": "",
        })()
        self.widgets = {
            "game_delete_source": type("Widget", (), {"get": lambda self: 0})(),
            "game_suffix": type("Widget", (), {"get": lambda self: "_nrm"})(),
            "pbr_delete_source": type("Widget", (), {"get": lambda self: 0})(),
            "normal_type": type("Widget", (), {"get": lambda self: "directx"})(),
            "resolution": type("Widget", (), {"get": lambda self: "auto"})(),
            "make_paa": type("Widget", (), {"get": lambda self: 0})(),
            "paa_path": type("Widget", (), {"get": lambda self: ""})(),
            "game_status": type("Widget", (), {"configure": lambda self, **kwargs: None})(),
            "pbr_status": type("Widget", (), {"configure": lambda self, **kwargs: None})(),
        }
        self.rendered = []
        self.updated = False
        self.work = None
        self.saved_game_suffix = False
        self.saved_game_output_suffixes = False
        self.saved_pbr_suffixes = False
        self.saved_pbr_naming = False

    def _render_pending(self, key, paths):
        self.rendered.append((key, paths))

    def _pbr_pending_paths(self):
        return list(self.pbr_pending_paths)

    def _game_pending_paths(self):
        return list(self.game_pending_paths)

    def _update_status_labels(self):
        self.updated = True

    def _save_current_game_suffix(self):
        self.saved_game_suffix = True

    def _save_current_game_output_suffixes(self):
        self.saved_game_output_suffixes = True

    def _save_pbr_suffixes(self):
        self.saved_pbr_suffixes = True

    def _save_pbr_naming(self):
        self.saved_pbr_naming = True

    def _suffix_error(self, suffixes):
        return ""

    def _start_progress(self, progress_key):
        pass

    def _progress_callback(self, progress_key):
        return None

    def _run_async(self, work, status_key, progress_key):
        self.work = work


class DummyEvent:
    def __init__(self, data):
        self.data = data


class DummyDropWidget:
    def __init__(self, children=None):
        self.children = children or []
        self.registered = []
        self.bound = []

    def drop_target_register(self, target):
        self.registered.append(target)

    def dnd_bind(self, event_name, handler):
        self.bound.append((event_name, handler))

    def winfo_children(self):
        return self.children


class UIDragDropTests(unittest.TestCase):
    def test_pbr_drop_accepts_image_file_by_using_parent_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "Door_BaseColor.png"
            image.write_bytes(b"png")
            app = DummyApp()

            main_window.DayZTextureToolApp._on_pbr_drop(app, DummyEvent(str(image)))

            self.assertEqual(app.pbr_folder, root)
            self.assertEqual(app.pbr_root_context, root)
            self.assertEqual(app.pbr_pending_paths, [image])
            self.assertEqual(app.pbr_selected_paths, {image})
            self.assertTrue(app.updated)

    def test_register_drop_target_applies_to_child_widgets(self):
        child = DummyDropWidget()
        parent = DummyDropWidget([child])
        handler = object()

        main_window._register_drop_target(parent, "DND_FILES", handler)

        for widget in [parent, child]:
            self.assertEqual(widget.registered, ["DND_FILES"])
            self.assertEqual(widget.bound, [("<<Drop>>", handler)])

    def test_pending_paths_default_to_selected_and_clear_selected_removes_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one.png"
            two = root / "two.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()

            main_window.DayZTextureToolApp._set_pending_paths(app, "game", [one, two])
            main_window.DayZTextureToolApp._select_pending_path(app, "game", two, False)
            main_window.DayZTextureToolApp._clear_selected_pending(app, "game")

            self.assertEqual(app.game_pending_paths, [two])
            self.assertEqual(app.game_selected_paths, set())

    def test_select_all_pending_selects_every_visible_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one.png"
            two = root / "two.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()

            main_window.DayZTextureToolApp._set_pending_paths(app, "game", [one, two])
            main_window.DayZTextureToolApp._set_all_pending(app, "game", False)
            main_window.DayZTextureToolApp._set_all_pending(app, "game", True)

            self.assertEqual(app.game_selected_paths, {one, two})

    def test_game_process_selected_uses_current_processor_and_selected_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one.png"
            two = root / "two.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()
            main_window.DayZTextureToolApp._set_pending_paths(app, "game", [one, two])
            main_window.DayZTextureToolApp._select_pending_path(app, "game", two, False)

            with patch("dayz_texture_tool.ui.main_window.save_settings"), patch("dayz_texture_tool.ui.main_window.process_game2pbr_files") as process:
                main_window.DayZTextureToolApp._start_game2pbr_selected(app)
                app.work()

            process.assert_called_once()
            self.assertEqual(process.call_args.args[0], [one])
            self.assertEqual(process.call_args.args[1], "DF_NRM")

    def test_game_process_all_selects_all_before_processing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one.png"
            two = root / "two.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()
            main_window.DayZTextureToolApp._set_pending_paths(app, "game", [one, two])
            main_window.DayZTextureToolApp._select_pending_path(app, "game", two, False)

            with patch("dayz_texture_tool.ui.main_window.save_settings"), patch("dayz_texture_tool.ui.main_window.process_game2pbr_files") as process:
                main_window.DayZTextureToolApp._start_game2pbr_all(app)
                app.work()

            self.assertEqual(app.game_selected_paths, {one, two})
            self.assertEqual(process.call_args.args[0], [one, two])

    def test_select_specific_images_selects_matching_pending_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match = root / "part_NRM.png"
            other = root / "part_MRA.png"
            match.write_bytes(b"png")
            other.write_bytes(b"png")
            app = DummyApp()
            main_window.DayZTextureToolApp._set_pending_paths(app, "game", [match, other])
            main_window.DayZTextureToolApp._set_all_pending(app, "game", False)

            main_window.DayZTextureToolApp._select_matching_game_suffixes(app)

            self.assertEqual(app.game_selected_paths, {match})

    def test_pbr_process_selected_uses_selected_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one_BaseColor.png"
            two = root / "one_Normal.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()
            app.pbr_root_context = root
            main_window.DayZTextureToolApp._set_pending_paths(app, "pbr", [one, two])
            main_window.DayZTextureToolApp._select_pending_path(app, "pbr", two, False)

            with patch("dayz_texture_tool.ui.main_window.save_settings"), patch("dayz_texture_tool.ui.main_window.convert_pbr_files") as process:
                main_window.DayZTextureToolApp._start_pbr2dayz_selected(app)
                app.work()

            process.assert_called_once()
            self.assertEqual(process.call_args.args[0], [one])
            self.assertEqual(process.call_args.kwargs["root_context"], root)


if __name__ == "__main__":
    unittest.main()
