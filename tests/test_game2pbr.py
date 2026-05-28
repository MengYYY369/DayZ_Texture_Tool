import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.processors.game2pbr import process_game2pbr


def make_rgba(path):
    arr = np.array([[[10, 20, 30, 40], [50, 60, 70, 80]]], dtype=np.uint8)
    Image.fromarray(arr, "RGBA").save(path)
    return arr


class Game2PBRTests(unittest.TestCase):
    def test_split_color_alpha_writes_rgb_and_alpha_next_to_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tex.png"
            arr = make_rgba(src)

            result = process_game2pbr(src, "SplitColorAlphaProcessor")

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["tex_rgb.png", "tex_alpha.png"])
            rgb = np.array(Image.open(Path(tmp) / "tex_rgb.png"))
            alpha = np.array(Image.open(Path(tmp) / "tex_alpha.png"))
            self.assertTrue(np.array_equal(rgb[0, 0, :3], arr[0, 0, :3]))
            self.assertEqual(int(rgb[0, 0, 3]), 255)
            self.assertEqual(int(alpha[0, 0, 0]), int(arr[0, 0, 3]))
            self.assertEqual(int(alpha[0, 0, 1]), int(arr[0, 0, 3]))

    def test_split_rgba_writes_four_channel_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tex.png"
            make_rgba(src)

            result = process_game2pbr(src, "SplitRGBAProcessor")

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["tex_r.png", "tex_g.png", "tex_b.png", "tex_a.png"])
            red = np.array(Image.open(Path(tmp) / "tex_r.png"))
            self.assertEqual(int(red[0, 0, 0]), 10)
            self.assertEqual(int(red[0, 0, 1]), 10)

    def test_split_rgba_accepts_custom_output_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tex.png"
            make_rgba(src)

            result = process_game2pbr(src, "SplitRGBAProcessor", output_suffixes={"r": "_red", "g": "_green", "b": "_blue", "a": "_mask"})

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["tex_red.png", "tex_green.png", "tex_blue.png", "tex_mask.png"])

    def test_merge_rgba_uses_matching_a_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tex.png"
            alpha = Path(tmp) / "tex_a.png"
            make_rgba(src)
            Image.fromarray(np.array([[[90, 90, 90, 255]]], dtype=np.uint8), "RGBA").save(alpha)

            result = process_game2pbr(src, "MergeRGBAProcessor")

            self.assertTrue(result.success)
            out = np.array(Image.open(Path(tmp) / "tex_merged.png"))
            self.assertEqual(int(out[0, 0, 3]), 90)

    def test_df_nrm_channel_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "part_NRM.png"
            make_rgba(src)

            result = process_game2pbr(src, "DF_NRM")

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["part_NRM_Metal.png", "part_NRM_Rou.png", "part_NRM_N.png"])
            metal = np.array(Image.open(Path(tmp) / "part_NRM_Metal.png"))
            rou = np.array(Image.open(Path(tmp) / "part_NRM_Rou.png"))
            normal = np.array(Image.open(Path(tmp) / "part_NRM_N.png"))
            self.assertEqual(int(metal[0, 0, 0]), 40)
            self.assertEqual(int(rou[0, 0, 0]), 30)
            self.assertEqual(int(normal[0, 0, 0]), 10)
            self.assertEqual(int(normal[0, 0, 1]), 20)
            self.assertEqual(int(normal[0, 0, 2]), 255)

    def test_df_nrm_accepts_custom_output_suffixes(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "part_NRM.png"
            make_rgba(src)

            result = process_game2pbr(src, "DF_NRM", output_suffixes={"metal": "_metx", "roughness": "_roux", "normal": "_normalx"})

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["part_NRM_metx.png", "part_NRM_roux.png", "part_NRM_normalx.png"])

    def test_abi_orn_channel_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "part_ORN.png"
            make_rgba(src)

            result = process_game2pbr(src, "ABI_ORN")

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["part_ORN_Rou.png", "part_ORN_AO.png", "part_ORN_N.png"])
            rou = np.array(Image.open(Path(tmp) / "part_ORN_Rou.png"))
            ao = np.array(Image.open(Path(tmp) / "part_ORN_AO.png"))
            normal = np.array(Image.open(Path(tmp) / "part_ORN_N.png"))
            self.assertEqual(int(rou[0, 0, 0]), 20)
            self.assertEqual(int(ao[0, 0, 0]), 10)
            self.assertEqual(int(normal[0, 0, 0]), 40)
            self.assertEqual(int(normal[0, 0, 1]), 30)
            self.assertEqual(int(normal[0, 0, 2]), 128)

    def test_df_mra_renames_channels_without_deleting_source_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "part_MRA.png"
            make_rgba(src)

            result = process_game2pbr(src, "DF_MRA")

            self.assertTrue(result.success)
            self.assertTrue(src.exists())
            self.assertEqual([p.name for p in result.outputs], ["part_MRA_met.png", "part_MRA_rou.png", "part_MRA_ao.png"])
            self.assertTrue((Path(tmp) / "part_MRA_met.png").exists())
            self.assertTrue((Path(tmp) / "part_MRA_rou.png").exists())
            self.assertTrue((Path(tmp) / "part_MRA_ao.png").exists())

    def test_direct_convert_does_not_overwrite_same_extension_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tex.png"
            make_rgba(src)

            result = process_game2pbr(src, "DirectConvertProcessor")

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["tex_converted.png"])
            self.assertTrue(src.exists())
            self.assertTrue((Path(tmp) / "tex_converted.png").exists())

    def test_xy_normal_moves_source_to_recycle_bin_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "normal.png"
            make_rgba(src)

            with patch("dayz_texture_tool.processors.game2pbr.move_to_recycle_bin") as recycle:
                result = process_game2pbr(src, "XYNormalMapProcessor", delete_source=True)

            self.assertTrue(result.success)
            recycle.assert_called_once_with(src)
            self.assertTrue((Path(tmp) / "normal_normal.png").exists())

    def test_df_mra_moves_source_to_recycle_bin_when_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "part_MRA.png"
            make_rgba(src)

            with patch("dayz_texture_tool.processors.game2pbr.move_to_recycle_bin") as recycle:
                result = process_game2pbr(src, "DF_MRA", delete_source=True)

            self.assertTrue(result.success)
            recycle.assert_called_once_with(src)
            self.assertEqual([p.name for p in result.outputs], ["part_MRA_met.png", "part_MRA_rou.png", "part_MRA_ao.png"])

    def test_xy_normal_accepts_custom_output_suffix(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "normal.png"
            make_rgba(src)

            result = process_game2pbr(src, "XYNormalMapProcessor", output_suffixes={"normal": "_nrm"})

            self.assertTrue(result.success)
            self.assertEqual([p.name for p in result.outputs], ["normal_nrm.png"])


if __name__ == "__main__":
    unittest.main()
