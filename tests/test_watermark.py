import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.processors.watermark import add_watermark, detect_watermark


class FakeWaterMark:
    def __init__(self, password_img=1, password_wm=1, processes=None):
        self.password_img = password_img
        self.password_wm = password_wm
        self.processes = processes
        self.wm_bit = [1, 0, 1, 1]

    def read_img(self, filename):
        self.filename = filename

    def read_wm(self, watermark, mode="str"):
        self.watermark = watermark
        self.mode = mode

    def embed(self, output):
        Path(output).write_bytes(b"watermarked")

    def extract(self, filename, wm_shape, mode="str"):
        return "hidden-text"


class WatermarkProcessorTests(unittest.TestCase):
    def test_add_watermark_writes_output_and_reports_bit_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.png"
            output = root / "source_watermarked.png"
            image.write_bytes(b"image")

            with patch("dayz_texture_tool.processors.watermark.WaterMark", FakeWaterMark):
                result = add_watermark(image, "secret", "7", output)

            self.assertTrue(result.success)
            self.assertEqual(result.outputs, [output])
            self.assertEqual(result.metadata["watermark_length"], 4)
            self.assertTrue(output.exists())

    def test_add_watermark_rejects_empty_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "source.png"
            image.write_bytes(b"image")

            result = add_watermark(image, "", "1")

            self.assertFalse(result.success)
            self.assertIn("Watermark content is empty", result.error)

    def test_add_watermark_rejects_paa_until_decode_tool_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "source.paa"
            image.write_bytes(b"paa")

            result = add_watermark(image, "secret", "1")

            self.assertFalse(result.success)
            self.assertIn("PAA watermarking requires a PAA decode tool", result.error)

    def test_detect_watermark_requires_positive_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "source.png"
            image.write_bytes(b"image")

            result = detect_watermark(image, "1", 0)

            self.assertFalse(result.success)
            self.assertIn("Watermark length must be greater than 0", result.error)

    def test_detect_watermark_reports_extracted_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "source.png"
            image.write_bytes(b"image")

            with patch("dayz_texture_tool.processors.watermark.WaterMark", FakeWaterMark):
                result = detect_watermark(image, "7", 4)

            self.assertTrue(result.success)
            self.assertEqual(result.metadata["watermark_text"], "hidden-text")

    def test_add_watermark_tga_uses_readable_intermediate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.tga"
            Image.new("RGB", (128, 128), (20, 80, 140)).save(image, "TGA")

            result = add_watermark(image, "secret", "7")

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.outputs, [root / "source_watermarked.tga"])
            self.assertTrue(result.outputs[0].exists())

            readable = root / "source_watermarked.png"
            Image.open(result.outputs[0]).save(readable, "PNG")
            detected = detect_watermark(readable, "7", result.metadata["watermark_length"])
            self.assertTrue(detected.success, detected.error)
            self.assertEqual(detected.metadata["watermark_text"], "secret")


if __name__ == "__main__":
    unittest.main()
