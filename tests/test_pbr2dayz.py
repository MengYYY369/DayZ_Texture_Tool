import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.processors.pbr2dayz import convert_pbr_folder, scan_pbr_groups


def save_rgb(path, color):
    arr = np.full((2, 2, 3), color, dtype=np.uint8)
    Image.fromarray(arr, "RGB").save(path)


class PBR2DayZTests(unittest.TestCase):
    def test_scan_groups_pbr_textures_by_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_rgb(root / "TestMat_BaseColor.png", [100, 90, 80])
            save_rgb(root / "TestMat_Normal_OGL.png", [127, 127, 255])
            save_rgb(root / "TestMat_Roughness.png", [64, 64, 64])
            save_rgb(root / "TestMat_Metallic.png", [20, 20, 20])
            save_rgb(root / "TestMat_AO.png", [200, 200, 200])

            groups = scan_pbr_groups(root)

            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].prefix, root.name)
            self.assertIn("basecolor", groups[0].textures)
            self.assertIn("normal", groups[0].textures)
            self.assertIn("roughness", groups[0].textures)
            self.assertIn("metallic", groups[0].textures)
            self.assertIn("ao", groups[0].textures)

    def test_convert_pbr_folder_writes_dayz_tga_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_rgb(root / "TestMat_BaseColor.png", [100, 90, 80])
            save_rgb(root / "TestMat_Normal_OGL.png", [127, 127, 255])
            save_rgb(root / "TestMat_Roughness.png", [64, 64, 64])
            save_rgb(root / "TestMat_Metallic.png", [20, 20, 20])
            save_rgb(root / "TestMat_AO.png", [200, 200, 200])

            result = convert_pbr_folder(root, normal_type="opengl", make_paa=False)

            self.assertTrue(result.success)
            self.assertEqual(result.total, 1)
            expected = [f"{root.name}_co.tga", f"{root.name}_nohq.tga", f"{root.name}_smdi.tga", f"{root.name}_as.tga"]
            self.assertEqual([p.name for p in result.outputs], expected)
            for name in expected:
                self.assertTrue((root / name).exists())

    def test_convert_pbr_folder_uses_parent_name_for_data_folder_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data_dir = root / "MyAddon" / "data"
            data_dir.mkdir(parents=True)
            save_rgb(data_dir / "TestMat_BaseColor.png", [100, 90, 80])

            result = convert_pbr_folder(root, normal_type="opengl", make_paa=False)

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["MyAddon_co.tga"])
            self.assertTrue((data_dir / "MyAddon_co.tga").exists())

    def test_convert_pbr_folder_accepts_custom_output_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_rgb(root / "TestMat_BaseColor.png", [100, 90, 80])
            save_rgb(root / "TestMat_Normal_OGL.png", [127, 127, 255])

            result = convert_pbr_folder(root, output_suffixes={"co": "_colorx", "nohq": "_normalx"})

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], [f"{root.name}_colorx.tga", f"{root.name}_normalx.tga"])

    def test_convert_pbr_folder_supports_prefix_modes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = root / "Parent" / "Child"
            folder.mkdir(parents=True)
            save_rgb(folder / "TestMat_BaseColor.png", [100, 90, 80])

            current = convert_pbr_folder(root, prefix_mode="current_folder")
            parent = convert_pbr_folder(root, prefix_mode="parent_folder")
            custom = convert_pbr_folder(root, prefix_mode="custom", custom_prefix="FixedName")

            self.assertTrue((folder / "Child_co.tga").exists())
            self.assertTrue((folder / "Parent_co.tga").exists())
            self.assertTrue((folder / "FixedName_co.tga").exists())
            self.assertEqual([p.name for p in current.outputs], ["Child_co.tga"])
            self.assertEqual([p.name for p in parent.outputs], ["Parent_co.tga"])
            self.assertEqual([p.name for p in custom.outputs], ["FixedName_co.tga"])

    def test_pbr_progress_callback_reports_each_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "One"
            two = root / "Two"
            one.mkdir()
            two.mkdir()
            save_rgb(one / "TestMat_BaseColor.png", [100, 90, 80])
            save_rgb(two / "TestMat_BaseColor.png", [50, 40, 30])
            events = []

            convert_pbr_folder(root, progress_callback=lambda done, total, label: events.append((done, total, label)))

            self.assertEqual([(done, total) for done, total, _ in events], [(1, 2), (2, 2)])

    def test_convert_pbr_folder_accepts_custom_suffix_patterns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_rgb(root / "TestMat_BC.png", [100, 90, 80])
            save_rgb(root / "TestMat_NX.png", [127, 127, 255])
            save_rgb(root / "TestMat_RH.png", [64, 64, 64])
            save_rgb(root / "TestMat_MT.png", [20, 20, 20])
            save_rgb(root / "TestMat_OCCX.png", [200, 200, 200])

            result = convert_pbr_folder(
                root,
                normal_type="opengl",
                make_paa=False,
                patterns={
                    "basecolor": ["_BC"],
                    "normal": ["_NX"],
                    "roughness": ["_RH"],
                    "metallic": ["_MT"],
                    "ao": ["_OCCX"],
                },
            )

            self.assertTrue(result.success)
            expected = [f"{root.name}_co.tga", f"{root.name}_nohq.tga", f"{root.name}_smdi.tga", f"{root.name}_as.tga"]
            self.assertEqual([p.name for p in result.outputs], expected)

    def test_convert_pbr_folder_fuzzy_match_finds_embedded_suffix_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_rgb(root / "T_VMGen_BaseColorMap_440cebeff58d4ce0cf503201272199da.png", [100, 90, 80])

            exact = convert_pbr_folder(root, patterns={"basecolor": ["basecolormap"]}, match_mode="exact")
            self.assertEqual(exact.outputs, [])

            fuzzy = convert_pbr_folder(root, patterns={"basecolor": ["basecolormap"]}, match_mode="fuzzy")
            self.assertTrue(fuzzy.success)
            self.assertEqual([p.name for p in fuzzy.outputs], [f"{root.name}_co.tga"])

    def test_invalid_paa_path_does_not_block_tga_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_rgb(root / "TestMat_BaseColor.png", [100, 90, 80])

            result = convert_pbr_folder(root, make_paa=True, image_to_paa=Path(tmp) / "missing.exe")

            self.assertTrue(result.success)
            self.assertTrue((root / f"{root.name}_co.tga").exists())
            self.assertTrue(any("ImageToPAA" in message for message in result.messages))

    def test_convert_pbr_folder_can_delete_source_textures_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "TestMat_BaseColor.png"
            rough = root / "TestMat_Roughness.png"
            save_rgb(base, [100, 90, 80])
            save_rgb(rough, [64, 64, 64])

            result = convert_pbr_folder(root, delete_source=True)

            self.assertTrue(result.success)
            self.assertFalse(base.exists())
            self.assertFalse(rough.exists())
            self.assertTrue((root / f"{root.name}_co.tga").exists())
            self.assertTrue((root / f"{root.name}_smdi.tga").exists())

    def test_convert_pbr_folder_deletes_tga_after_paa_when_delete_source_is_enabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "TestMat_BaseColor.png"
            save_rgb(base, [100, 90, 80])
            image_to_paa = root / "ImageToPAA.exe"
            image_to_paa.write_text("stub", encoding="utf-8")

            def fake_paa(outputs, image_to_paa_path, messages):
                for output in outputs:
                    output.with_suffix(".paa").write_bytes(b"paa")

            with patch("dayz_texture_tool.processors.pbr2dayz._run_image_to_paa", fake_paa):
                result = convert_pbr_folder(root, make_paa=True, image_to_paa=image_to_paa, delete_source=True)

            self.assertTrue(result.success)
            self.assertFalse(base.exists())
            self.assertFalse((root / f"{root.name}_co.tga").exists())
            self.assertTrue((root / f"{root.name}_co.paa").exists())
            self.assertEqual([p.name for p in result.outputs], [f"{root.name}_co.paa"])


if __name__ == "__main__":
    unittest.main()
