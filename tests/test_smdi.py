import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.processors.smdi import (
    convert_color_to_smdi,
    convert_color_to_smdi_files,
    convert_smdi_pixels,
    smdi_output_stem,
)


def write_image(path: Path, pixels, size: int = 4) -> None:
    # 4x4 by default: PAA packing rejects anything that is not a multiple of 4.
    array = np.array([pixels], dtype=np.uint8).reshape(1, 1, 4)
    Image.fromarray(np.repeat(np.repeat(array, size, axis=0), size, axis=1), "RGBA").save(path)


class SmdiFormulaTests(unittest.TestCase):
    def test_formula_matches_specular_map_finish(self):
        pixels = np.array([
            [200, 128, 64, 255],
            [10, 0, 0, 255],
            [10, 255, 255, 255],
            [10, 255, 0, 255],
            [10, 1, 1, 255],
            [10, 77, 200, 255],
        ], dtype=np.uint8).reshape(1, 6, 4)

        converted = convert_smdi_pixels(pixels, 10.0)[0]

        self.assertEqual(converted.tolist(), [
            [127, 41, 64, 255],
            [255, 0, 0, 255],
            [0, 255, 255, 255],
            [0, 23, 0, 255],
            [254, 0, 1, 255],
            [178, 62, 200, 255],
        ])

    def test_formula_keeps_blue_and_forces_alpha(self):
        pixels = np.array([[[0, 128, 64, 0]]], dtype=np.uint8)

        converted = convert_smdi_pixels(pixels, 10.0)[0, 0]

        self.assertEqual(int(converted[2]), 64)
        self.assertEqual(int(converted[3]), 255)

    def test_zero_specular_power_collapses_to_green(self):
        pixels = np.array([[[0, 128, 64, 255]]], dtype=np.uint8)

        converted = convert_smdi_pixels(pixels, 0.0)[0, 0]

        self.assertEqual(converted.tolist(), [127, 128, 64, 255])

    def test_red_channel_is_inverse_of_green(self):
        pixels = np.zeros((1, 256, 4), dtype=np.uint8)
        pixels[0, :, 1] = np.arange(256)

        converted = convert_smdi_pixels(pixels, 10.0)[0]

        for green in range(256):
            self.assertEqual(int(converted[green, 0]), 255 - green)


class SmdiNamingTests(unittest.TestCase):
    def test_output_stem_strips_color_suffixes(self):
        self.assertEqual(smdi_output_stem(Path("xxx_co.paa")), "xxx_smdi")
        self.assertEqual(smdi_output_stem(Path("xxx_ca.png")), "xxx_smdi")
        self.assertEqual(smdi_output_stem(Path("xxx_CO.tga")), "xxx_smdi")
        self.assertEqual(smdi_output_stem(Path("xxx.png")), "xxx_smdi")
        self.assertEqual(smdi_output_stem(Path("xxx_smdi.paa")), "xxx_smdi_smdi")
        self.assertEqual(smdi_output_stem(Path("_co.paa")), "_co_smdi")


class SmdiConversionTests(unittest.TestCase):
    def test_conversion_writes_tga_next_to_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "armor_co.png"
            write_image(source, [0, 128, 64, 255])

            result = convert_color_to_smdi(source, specular_power=10.0)

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.outputs, [root / "armor_smdi.tga"])
            with Image.open(root / "armor_smdi.tga") as image:
                self.assertEqual(image.convert("RGBA").getpixel((0, 0)), (127, 41, 64, 255))

    def test_existing_output_is_overwritten_and_input_is_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "armor_co.png"
            write_image(source, [0, 128, 64, 255])
            original = source.read_bytes()
            (root / "armor_smdi.tga").write_bytes(b"stale")

            result = convert_color_to_smdi(source, specular_power=10.0)

            self.assertTrue(result.success, result.error)
            self.assertGreater((root / "armor_smdi.tga").stat().st_size, len("stale"))
            self.assertEqual(source.read_bytes(), original)

    def test_paa_input_requires_image_to_paa_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "armor_co.paa"
            source.write_bytes(b"paa")

            result = convert_color_to_smdi(source)

            self.assertFalse(result.success)
            self.assertIn("ImageToPAA.exe path is missing", result.error)

    def test_negative_specular_power_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "armor_co.png"
            source.write_bytes(b"png")

            result = convert_color_to_smdi(source, specular_power=-1)

            self.assertFalse(result.success)
            self.assertIn("Specular power", result.error)

    def test_non_numeric_specular_power_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "armor_co.png"
            source.write_bytes(b"png")

            result = convert_color_to_smdi(source, specular_power="abc")

            self.assertFalse(result.success)
            self.assertIn("must be a number", result.error)

    def test_unsupported_extension_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "armor_co.dds"
            source.write_bytes(b"dds")

            result = convert_color_to_smdi(source)

            self.assertFalse(result.success)
            self.assertIn("Unsupported image extension", result.error)

    def test_make_paa_packs_paa_and_leaves_no_tga(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "armor_co.png"
            write_image(source, [0, 128, 64, 255])
            calls = []

            def fake_run(tool_path, source_path, output_path):
                calls.append((Path(source_path).name, Path(output_path).name))
                Path(output_path).write_bytes(b"paa")

            with patch("dayz_texture_tool.processors.smdi._run_image_to_paa", fake_run):
                result = convert_color_to_smdi(source, specular_power=10.0, make_paa=True, image_to_paa=root / "ImageToPAA.exe")

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.outputs, [root / "armor_smdi.paa"])
            self.assertTrue((root / "armor_smdi.paa").exists())
            self.assertFalse((root / "armor_smdi.tga").exists())
            self.assertEqual(calls, [("armor_smdi.tga", "armor_smdi.paa")])

    def test_make_paa_removes_previous_tga(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "armor_co.png"
            write_image(source, [0, 128, 64, 255])
            (root / "armor_smdi.tga").write_bytes(b"stale")

            def fake_run(tool_path, source_path, output_path):
                Path(output_path).write_bytes(b"paa")

            with patch("dayz_texture_tool.processors.smdi._run_image_to_paa", fake_run):
                result = convert_color_to_smdi(source, specular_power=10.0, make_paa=True, image_to_paa=root / "ImageToPAA.exe")

            self.assertTrue(result.success, result.error)
            self.assertFalse((root / "armor_smdi.tga").exists())

    def test_make_paa_rejects_size_that_is_not_a_multiple_of_four(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "armor_co.png"
            Image.fromarray(np.zeros((3, 3, 4), dtype=np.uint8), "RGBA").save(source)

            with patch("dayz_texture_tool.processors.smdi._run_image_to_paa") as packer:
                result = convert_color_to_smdi(source, specular_power=10.0, make_paa=True, image_to_paa=root / "ImageToPAA.exe")

            self.assertFalse(result.success)
            self.assertIn("multiples of 4", result.error)
            packer.assert_not_called()
            self.assertFalse((root / "armor_smdi.paa").exists())
            self.assertFalse((root / "armor_smdi.tga").exists())

    def test_paa_input_is_decoded_through_the_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "armor_co.paa"
            source.write_bytes(b"paa")
            tool = root / "ImageToPAA.exe"
            tool.write_bytes(b"exe")
            calls = []

            def fake_run(tool_path, source_path, output_path):
                calls.append((Path(source_path).suffix, Path(output_path).suffix))
                write_image(Path(output_path), [0, 128, 64, 255])

            with patch("dayz_texture_tool.processors.smdi._run_image_to_paa", fake_run):
                result = convert_color_to_smdi(source, specular_power=10.0, image_to_paa=tool)

            self.assertTrue(result.success, result.error)
            self.assertEqual(calls, [(".paa", ".png")])
            self.assertEqual(result.outputs, [root / "armor_smdi.tga"])

    def test_batch_reports_progress(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "one_co.png"
            second = root / "two_co.png"
            for path in (first, second):
                write_image(path, [0, 128, 64, 255])
            seen = []

            result = convert_color_to_smdi_files([first, second], specular_power=10.0, progress_callback=lambda done, total, name: seen.append((done, total, name)))

            self.assertEqual(result.total, 2)
            self.assertEqual(result.succeeded, 2)
            self.assertEqual(seen, [(1, 2, "one_co.png"), (2, 2, "two_co.png")])

    def test_batch_continues_after_a_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            good = root / "one_co.png"
            bad = root / "two_co.dds"
            write_image(good, [0, 128, 64, 255])
            bad.write_bytes(b"dds")
            seen = []

            result = convert_color_to_smdi_files([good, bad], specular_power=10.0, progress_callback=lambda done, total, name: seen.append(name))

            self.assertEqual(result.total, 2)
            self.assertEqual(result.succeeded, 1)
            self.assertEqual(result.failed, 1)
            self.assertEqual(seen, ["one_co.png", "two_co.dds"])

    def test_batch_rejects_duplicate_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "armor_co.png"
            second = root / "armor_ca.png"
            for path in (first, second):
                write_image(path, [0, 128, 64, 255])

            result = convert_color_to_smdi_files([first, second], specular_power=10.0)

            self.assertEqual(result.succeeded, 1)
            self.assertEqual(result.failed, 1)
            self.assertIn("already produced by", result.results[1].error)

    def test_batch_rejects_output_that_would_overwrite_another_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "armor_co.png"
            second = root / "armor_smdi.tga"
            write_image(first, [0, 128, 64, 255])
            write_image(second, [0, 128, 64, 255])

            result = convert_color_to_smdi_files([first, second], specular_power=10.0)

            self.assertEqual(result.failed, 1)
            self.assertEqual(result.succeeded, 1)
            self.assertIn("would overwrite another input", result.results[0].error)
            self.assertTrue((root / "armor_smdi_smdi.tga").exists())


if __name__ == "__main__":
    unittest.main()
