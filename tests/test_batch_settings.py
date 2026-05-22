import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.batch import collect_image_files, process_game2pbr_auto
from dayz_texture_tool.settings import AppSettings, load_settings, save_settings


def make_rgba(path):
    arr = np.array([[[10, 20, 30, 40]]], dtype=np.uint8)
    Image.fromarray(arr, "RGBA").save(path)


class BatchAndSettingsTests(unittest.TestCase):
    def test_collect_image_files_recurses_supported_extensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            nested = root / "data"
            nested.mkdir()
            make_rgba(root / "a_NRM.png")
            make_rgba(nested / "b_ORN.tga")
            (root / "notes.txt").write_text("skip", encoding="utf-8")

            files = collect_image_files(root)

            self.assertEqual([p.name for p in files], ["a_NRM.png", "b_ORN.tga"])

    def test_auto_game2pbr_matches_suffixes_and_skips_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_rgba(root / "a_NRM.png")
            make_rgba(root / "b_ORN.png")
            make_rgba(root / "c_unknown.png")

            result = process_game2pbr_auto(root)

            self.assertEqual(result.total, 3)
            self.assertEqual(result.succeeded, 2)
            self.assertEqual(result.skipped, 1)
            self.assertTrue((root / "a_NRM_N.png").exists())
            self.assertTrue((root / "b_ORN_N.png").exists())
            self.assertTrue(any("skipped" in message.lower() for message in result.messages))

    def test_auto_game2pbr_accepts_custom_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_rgba(root / "a_NormalPacked.png")
            make_rgba(root / "b_MaterialPack.png")

            result = process_game2pbr_auto(root, suffix_map={"DF_NRM": ["_normalpacked"], "DF_MRA": ["_materialpack"]})

            self.assertEqual(result.total, 2)
            self.assertEqual(result.succeeded, 2)
            self.assertTrue((root / "a_NormalPacked_N.png").exists())
            self.assertFalse((root / "b_MaterialPack.png").exists())
            self.assertTrue((root / "b_MaterialPack_met.png").exists())

    def test_auto_game2pbr_fuzzy_match_finds_embedded_suffix_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "T_VMGen_MRAMap_440cebeff58d4ce0cf503201272199da.png"
            make_rgba(source)

            exact = process_game2pbr_auto(root, suffix_map={"DF_MRA": ["mramap"]}, match_mode="exact")
            self.assertEqual(exact.skipped, 1)

            fuzzy = process_game2pbr_auto(root, suffix_map={"DF_MRA": ["mramap"]}, match_mode="fuzzy")
            self.assertEqual(fuzzy.succeeded, 1)
            self.assertFalse(source.exists())
            self.assertTrue((root / "T_VMGen_MRAMap_440cebeff58d4ce0cf503201272199da_met.png").exists())

    def test_settings_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = AppSettings(
                image_to_paa="D:/tools/ImageToPAA.exe",
                language="en",
                game_suffixes={"DF_MRA": ["_materialpack"]},
                pbr_suffixes={"basecolor": ["_bc"], "normal": ["_nrmx"]},
                game_match_mode="fuzzy",
                pbr_match_mode="exact",
            )

            save_settings(settings, path)
            loaded = load_settings(path)

            self.assertEqual(loaded.image_to_paa, "D:/tools/ImageToPAA.exe")
            self.assertEqual(loaded.language, "en")
            self.assertEqual(loaded.game_suffixes["DF_MRA"], ["_materialpack"])
            self.assertEqual(loaded.pbr_suffixes["basecolor"], ["_bc"])
            self.assertEqual(loaded.pbr_suffixes["normal"], ["_nrmx"])
            self.assertEqual(loaded.game_match_mode, "fuzzy")
            self.assertEqual(loaded.pbr_match_mode, "exact")


if __name__ == "__main__":
    unittest.main()
