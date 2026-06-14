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

    def test_add_watermark_accepts_text_password(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.png"
            Image.new("RGB", (128, 128), (40, 90, 160)).save(image, "PNG")

            result = add_watermark(image, "secret", "MengYYY")

            self.assertTrue(result.success, result.error)
            detected = detect_watermark(result.outputs[0], "MengYYY", result.metadata["watermark_length"])
            self.assertTrue(detected.success, detected.error)
            self.assertEqual(detected.metadata["watermark_text"], "secret")

    def test_add_watermark_rejects_paa_until_decode_tool_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "source.paa"
            image.write_bytes(b"paa")

            result = add_watermark(image, "secret", "1")

            self.assertFalse(result.success)
            self.assertIn("ImageToPAA.exe path is missing", result.error)

    def test_add_watermark_paa_uses_temporary_png_and_converts_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.paa"
            image.write_bytes(b"paa")
            image_to_paa = root / "ImageToPAA.exe"
            image_to_paa.write_text("stub", encoding="utf-8")
            written = []

            def fake_run(command, **kwargs):
                written.append([Path(part).name for part in command])
                if len(written) == 1:
                    Path(command[2]).write_bytes(b"png")
                else:
                    Path(command[2]).write_bytes(b"watermarked paa")
                return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch("dayz_texture_tool.processors.watermark.subprocess.run", fake_run), patch("dayz_texture_tool.processors.watermark.WaterMark", FakeWaterMark):
                result = add_watermark(image, "secret", "1", image_to_paa=image_to_paa)

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.outputs, [root / "source_watermarked.paa"])
            self.assertEqual((root / "source_watermarked.paa").read_bytes(), b"watermarked paa")
            self.assertEqual(written[0][0], "ImageToPAA.exe")
            self.assertEqual(written[0][1], "source.paa")
            self.assertEqual(written[1][0], "ImageToPAA.exe")
            self.assertEqual(written[1][2], "source_watermarked.paa")

    def test_add_watermark_paa_can_overwrite_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.paa"
            image.write_bytes(b"paa")
            image_to_paa = root / "ImageToPAA.exe"
            image_to_paa.write_text("stub", encoding="utf-8")

            def fake_run(command, **kwargs):
                if Path(command[1]).suffix.lower() == ".paa":
                    Path(command[2]).write_bytes(b"png")
                else:
                    Path(command[2]).write_bytes(b"overwritten paa")
                return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch("dayz_texture_tool.processors.watermark.subprocess.run", fake_run), patch("dayz_texture_tool.processors.watermark.WaterMark", FakeWaterMark):
                result = add_watermark(image, "secret", "1", image_to_paa=image_to_paa, overwrite=True)

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.outputs, [image])
            self.assertEqual(image.read_bytes(), b"overwritten paa")

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

    def test_detect_watermark_paa_uses_temporary_png(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "source.paa"
            image.write_bytes(b"paa")
            image_to_paa = root / "ImageToPAA.exe"
            image_to_paa.write_text("stub", encoding="utf-8")
            calls = []

            def fake_run(command, **kwargs):
                calls.append([Path(part).name for part in command])
                Path(command[2]).write_bytes(b"png")
                return type("Completed", (), {"returncode": 0, "stderr": "", "stdout": ""})()

            with patch("dayz_texture_tool.processors.watermark.subprocess.run", fake_run), patch("dayz_texture_tool.processors.watermark.WaterMark", FakeWaterMark):
                result = detect_watermark(image, "7", 4, image_to_paa=image_to_paa)

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.metadata["watermark_text"], "hidden-text")
            self.assertEqual(calls[0][0], "ImageToPAA.exe")
            self.assertEqual(calls[0][1], "source.paa")

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
