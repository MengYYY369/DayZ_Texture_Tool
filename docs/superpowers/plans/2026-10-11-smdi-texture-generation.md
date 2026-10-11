# SMDI Texture Generation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click SMDI generator: take a DayZ color texture (`.paa` or a common image), apply the ImageToPAA `specularMapFinish` formula, write `<name>_smdi.tga`, and optionally pack it into `<name>_smdi.paa` with `ImageToPAA.exe`.

**Architecture:** All formula, naming, PAA decode/encode and batch logic lives in a new focused processor module `processors/smdi.py`; the UI only collects inputs, runs the batch in a worker thread and displays the result. The new `SMDI` page reuses the existing pending-list / progress / async machinery that the `Watermark` page already uses. `.paa` reading and writing always go through the `image_to_paa` path from Settings, **always with an explicit destination**, because `ImageToPAA.exe` destroys its source when the destination is omitted. Every file is written inside a temp directory first and only moved into the output folder after the external tool has actually produced it, so a silent tool failure can never leave a half-written or stale artifact behind.

**Tech Stack:** Python 3.10+, customtkinter, Pillow, numpy, unittest, CodeGraph CLI. **No new dependencies.**

---

## Verified Facts (evidence behind the design)

These were measured on this machine while designing the feature. They are the reason the design looks the way it does — do not "simplify" them away.

1. **The source formula** is the shipped filter `D:\steam\steamapps\common\DayZ Tools\Bin\ImageToPAA\Filters\specularMapFinish.bitfilt`:

   ```
   comment "define specular power";
   sp = 10;
   p = src pixel [u,v];
   x = 1 - green p;
   y = green p * ((sp * blue p + 1) / (sp + 1));
   c = color[x,y,blue p,1];
   ```

   `bitfilt` scripts operate on 0..1 floats; `color[r,g,b,a]` builds one RGBA pixel (`nmamplify.bitfilt` uses `c = color[x*0.5+0.5, z*0.5+0.5, y*0.5+0.5, 1]`, which only makes sense as an RGBA constructor). The reference implementation rounds half up.

2. **The formula really is the `_co` → `_smdi` transform.** Of 80 random `_co.paa` / `_smdi.paa` pairs under `D:/MY`, 15% match `specularMapFinish(co)` exactly (G vs `co.G*(10*co.B+255)/2805` MAD < 1, B vs `co.B` MAD < 1; e.g. `AK47_KurmakuPrestige_smdi.paa`), another 21% match on G only, and the rest are hand-painted or straight copies. 3090 of the 3224 `*_smdi.paa` files under `D:/MY` have a sibling color map. (Measured in an earlier pass while designing this feature; not re-measured during plan review, because it would mean decoding user assets.)

3. **Shipped SMDI PAAs have R = 255 and A = 255.** 245 of 250 randomly sampled `*_smdi.paa` files decode with a pure white R channel, and a DXT1 endpoint scan proves the data itself is white (not a decoder artifact), because `D:\steam\steamapps\common\DayZ Tools\Bin\ImageToPAA\TexConvert.cfg:209-219` declares:

   ```
   class specular_diffuseinverse_map {
       name = "*_smdi.*"; format = "DXT1"; enableDXT = 1;
       channelSwizzleR = "1"; channelSwizzleG = "G"; channelSwizzleB = "B"; channelSwizzleA = "1"; dynRange = 0;
   }
   ```

   So the formula's `R = 1-G` is computed and then overwritten when the image is packed into a PAA. **The R channel only survives in the intermediate `.tga`.** The `.tga` keeps `1-G` anyway (decision Q9) so it stays byte-identical to what ImageToPAA's own filter produces. (A separate `*_dtsmdi.*` rule exists at `TexConvert.cfg:164-175`.)

4. **The `*_smdi.*` rule keys on the DESTINATION filename, not on the source.** Measured with the real tool on temp copies:

   - `png_plain.png` → `png_plain_smdi.paa`: decoded R = 255 (swizzle applied, even though the source name has no `_smdi`).
   - `w_smdi.tga` → `nonsmdi_from_tga.paa`: decoded R = 11 (source name matched `*_smdi.*` but no swizzle — the source name is irrelevant).
   - `plan_smdi.tga` → `x_smdi.paa`: decoded R = 255.

   So what must match `*_smdi.*` is the **`.paa` we ask the tool to write**, which this plan always names `<stem>_smdi.paa`. The temp `.tga` name does not matter to `TexConvert.cfg`.

5. **`ImageToPAA.exe` CLI contract** (measured):

   - Usage `ImageToPAA.exe <source> [<destination>]`, prints `src->dst`, exit code 0 on success.
   - **With no destination it converts in place and destroys the source** (`solo.paa` → `solo.paa`). Always pass an explicit destination when decoding. Encoding may use the implicit `<stem>.paa` sibling, which is what `processors/pbr2dayz.py:219-229` does today. (Reported by the earlier measurement pass; deliberately *not* re-tested during plan review, because reproducing it means destroying a file.)
   - It overwrites an existing destination silently.
   - The destination extension picks the output format (`.png` / `.tga` decode, anything else writes PAA data).
   - **DXT1 output requires both dimensions to be multiples of 4.** Measured: 4x4, 8x8, 16x16, 4x8, 8x4 → exit 0. 3x3, 5x5, 6x6, 10x10, 12x12, 4x6, 6x4 → exit 1, no file. 1x1 and 2x2 → exit 1 **plus a bogus ~128-byte file**. Non-PAA output (`.tga` / `.png`) has no such constraint.
   - Therefore: always verify the destination exists **inside the temp directory** before moving it into place, so a silent failure can never be reported as a success over a stale file.

6. **The PAA round trip is lossy, the TGA is exact.** End-to-end run of this plan's code with the real tool on an 8x8 source (G=128, B=64, sp=10): the intermediate `.tga` came out exactly `(127, 41, 64, 255)`, but the packed `.paa` decoded as `(255, 42, 63, 255)` — DXT1 block compression moved G and B by one step. Do not write tests or acceptance criteria that expect the `.paa` channels to equal the formula exactly; only the `.tga` is exact.

7. Re-encoding an explicitly named `.paa` destination is already proven in this repo: `processors/watermark.py:101-113` round-trips a PAA through a temp directory the same way (`:110` decode, `:112` re-encode, `:113` move), and `processors/watermark.py:69-78` is the subprocess helper it uses.

## Settled Decisions (user interview)

| # | Decision |
|---|---|
| Q1 | New dedicated `SMDI` page: drop area + pending list + `Specular Power` entry + `Output PAA` checkbox + `Select Images`, plus clear / process-selected / process-all buttons, status label and progress bar |
| Q2 | Output `<name>_smdi.tga`; when `Output PAA` is checked, also run `ImageToPAA.exe` to produce `<name>_smdi.paa` |
| Q3 | Implement inside the existing Tkinter/customtkinter app; do not start the planned PyQt rewrite |
| Q4 | `sp` editable in the UI, default 10, persisted in settings |
| Q5 | Naming: strip a trailing `_co`/`_ca`, then append `_smdi` (`xxx_co.paa` → `xxx_smdi.paa`) |
| Q6 | When `Output PAA` is checked, no intermediate TGA is left behind — including a `.tga` left over from an earlier run |
| Q7 | Inputs: `.paa` plus common images (PNG/TGA/JPG/BMP/TIF) |
| Q8 | Silently overwrite existing outputs |
| Q9 | The intermediate TGA keeps the formula's `R = 1-G` |
| Q10 | Write this plan first, then have a sub-agent review it before implementing |

## Assumptions The Implementation Depends On

- The formula runs on 0..1 floats (8-bit input divided by 255), the result is rounded half up back to 8-bit (matching the bitfilt reference), and alpha is always 1 (255). A `_ca.paa` input contributes color only; its alpha is discarded.
- `specular_power` must be finite and ≥ 0. `sp = 0` degenerates to `y = green`; `sp = -1` divides by zero, so negative values are rejected.
- `Output PAA` additionally requires both image dimensions to be multiples of 4 (fact 5); anything else is a readable per-file error, not a partial write.
- Outputs are written next to the input file.
- PAA decode and PAA encode both use the `image_to_paa` path from Settings. A missing/invalid path is a **readable per-file error**, never a silent skip — this deliberately differs from `pbr2dayz._run_image_to_paa` (`processors/pbr2dayz.py:219-222`), which appends a message and skips, because here the PAA *is* the requested output.
- Per-file failure reasons must be visible in the status label: `_show_result` only prints the ok/fail/skip counts, so the SMDI page additionally surfaces the first failure's message.
- A batch never lets two inputs fight over one output, and never lets one input's output overwrite another input of the same batch (see the collision guard in Task 2).
- Batch behaviour matches the other pages: multi-select, folder drop, per-file progress, `BatchResult` summary, silent overwrite.
- Bilingual UI: new strings go into both `zh` and `en`.
- No new dependencies; tests use `unittest`.
- `PBR2DayZ`'s existing SMDI output (metal + roughness → smdi) is **not** touched.

## File Structure

- Create: `src/dayz_texture_tool/processors/smdi.py`
  - Owns the formula, output naming, PAA decode/encode, single-file and batch entry points.
- Modify: `src/dayz_texture_tool/settings.py`
  - Persist `smdi_specular_power`.
- Modify: `src/dayz_texture_tool/ui/i18n.py`
  - Add `smdi`, `drop_smdi_files`, `drop_smdi_files_hint`, `specular_power` to both languages. Preserve the file's current encoding; do not re-encode the whole file.
- Modify: `src/dayz_texture_tool/ui/main_window.py`
  - Add the `SMDI` navigation page, pending state, page builder, selection/drop handlers, start actions, settings save hook, and an optional result hook so per-file failures are readable.
- Create: `tests/test_smdi.py`
  - Formula, naming, single-file conversion, PAA decode/encode, size guard, collision guard, batch progress.
- Modify: `tests/test_batch_settings.py`
  - Persistence of `smdi_specular_power`.
- Modify: `tests/test_ui_dragdrop.py`
  - UI wiring for the SMDI page using the existing dummy-app style.

## Success Criteria

- Top navigation shows a fifth page `SMDI` (same label in both languages).
- The page accepts dropped/selected `.paa`, PNG, TGA, JPG, JPEG, BMP, TIF files and lists them in a pending panel with the same select/clear behaviour as the other pages.
- `Specular Power` defaults to 10 and is persisted; `Output PAA` is a checkbox on the page.
- Processing writes `<stem>_smdi.tga` next to the input, where a trailing `_co`/`_ca` is stripped from `<stem>` first. The TGA's R channel is `255 - G`, G is `G * ((sp * B + 1) / (sp + 1))`, B is unchanged, A is 255.
- With `Output PAA` checked, `<stem>_smdi.paa` is produced through `ImageToPAA.exe` and no `.tga` is left behind. (Its G/B are DXT1-compressed and therefore approximate — fact 6; its R and A are 255 — fact 3.)
- A `.paa` input without a configured `ImageToPAA.exe`, an invalid `sp`, a non-multiple-of-4 size with `Output PAA` checked, or a batch that would make two files fight over one output: each fails with a readable reason shown in the status label, without destroying any input.
- `python -m unittest tests.test_smdi tests.test_batch_settings` passes.
- CodeGraph index is synced after the code changes.

## Known Environment Limits (do not misreport)

`rtk python -m unittest discover tests` is the full suite. **Baseline before this work: 50 tests, 1 error + 2 failures, all pre-existing and environmental:**

- `ERROR: test_ui_dragdrop (unittest.loader._FailedTest.test_ui_dragdrop)` — `customtkinter` is not installed in the default Python 3.13 interpreter.
- `FAIL: test_add_watermark_accepts_text_password`, `FAIL: test_add_watermark_tga_uses_readable_intermediate` — `blind-watermark` is not installed.

Consequences:

- `tests/test_smdi.py` needs only numpy + Pillow (both installed) and **must** pass here.
- `tests/test_ui_dragdrop.py` cannot be imported in this environment. Run it only if `customtkinter` is importable; otherwise report it as **not executed** — never as passing.
- If the dependencies are installed (`rtk pip install -r requirements.txt`) run the full suite and expect it to be green apart from nothing: the two `blind-watermark` failures should then pass too.

---

## Task 1: Write The Processor Tests (red)

**Files:**

- Create: `tests/test_smdi.py`
- Later implementation target: `src/dayz_texture_tool/processors/smdi.py`

- [ ] **Step 1: Create the failing tests**

Create `tests/test_smdi.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.processors.smdi import convert_color_to_smdi, convert_color_to_smdi_files, convert_smdi_pixels, smdi_output_stem


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```powershell
rtk python -m unittest tests.test_smdi -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dayz_texture_tool.processors.smdi'`.

- [ ] **Step 3: Do not implement yet**

Stop after seeing the failure. Implementation happens in Task 2.

## Task 2: Implement The SMDI Processor

**Files:**

- Create: `src/dayz_texture_tool/processors/smdi.py`
- Test: `tests/test_smdi.py`

- [ ] **Step 1: Create the processor**

Create `src/dayz_texture_tool/processors/smdi.py`:

```python
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from dayz_texture_tool.models import BatchResult, ProcessingResult


SMDI_SUFFIX = "_smdi"
COLOR_MAP_SUFFIXES = ("_co", "_ca")
DEFAULT_SPECULAR_POWER = 10.0
SUPPORTED_SMDI_EXTENSIONS = {".paa", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".tga"}
PAA_BLOCK_SIZE = 4

ProgressCallback = Callable[[int, int, str], None]


def parse_specular_power(value: str | float) -> float:
    try:
        power = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Specular power must be a number.") from exc
    if not math.isfinite(power) or power < 0:
        raise ValueError("Specular power must be a finite number greater than or equal to 0.")
    return power


def smdi_output_stem(path: Path) -> str:
    stem = path.stem
    lowered = stem.lower()
    for suffix in COLOR_MAP_SUFFIXES:
        if lowered.endswith(suffix) and len(stem) > len(suffix):
            return f"{stem[: -len(suffix)]}{SMDI_SUFFIX}"
    return f"{stem}{SMDI_SUFFIX}"


def smdi_output_path(path: Path, make_paa: bool) -> Path:
    extension = ".paa" if make_paa else ".tga"
    return path.with_name(f"{smdi_output_stem(path)}{extension}")


def convert_smdi_pixels(pixels: np.ndarray, specular_power: float = DEFAULT_SPECULAR_POWER) -> np.ndarray:
    source = np.asarray(pixels, dtype=np.float32) / 255.0
    green = source[:, :, 1]
    blue = source[:, :, 2]
    red = 1.0 - green
    gloss = green * ((specular_power * blue + 1.0) / (specular_power + 1.0))
    alpha = np.ones_like(red)
    stacked = np.stack([red, gloss, blue, alpha], axis=-1)
    # bitfilt rounds half up, so np.rint (banker's rounding) is not equivalent at exact .5 ties.
    return np.clip(np.floor(stacked * 255.0 + 0.5), 0, 255).astype(np.uint8)


def _is_paa(path: Path) -> bool:
    return path.suffix.lower() == ".paa"


def _run_image_to_paa(tool_path: Path, source: Path, output: Path) -> None:
    if not tool_path.exists():
        raise FileNotFoundError(f"ImageToPAA.exe path is missing or invalid: {tool_path}")
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    completed = subprocess.run([str(tool_path), str(source), str(output)], **run_kwargs)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or f"{tool_path.name} failed with exit code {completed.returncode}.")


def _load_rgba(path: Path, tool_path: Path | None, tmp_root: Path) -> np.ndarray:
    if _is_paa(path):
        if tool_path is None:
            raise FileNotFoundError("ImageToPAA.exe path is missing or invalid.")
        readable = tmp_root / "input.png"
        _run_image_to_paa(tool_path, path, readable)
        if not readable.exists():
            raise RuntimeError(f"ImageToPAA.exe did not produce a readable image for {path.name}.")
        with Image.open(readable) as image:
            return np.array(image.convert("RGBA"), dtype=np.uint8)
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"), dtype=np.uint8)


def convert_color_to_smdi(input_path: str | Path, specular_power: str | float = DEFAULT_SPECULAR_POWER, make_paa: bool = False, image_to_paa: str | Path | None = None) -> ProcessingResult:
    start = time.time()
    path = Path(input_path)
    if path.suffix.lower() not in SUPPORTED_SMDI_EXTENSIONS:
        return ProcessingResult(False, input_path=path, processor="SMDI", elapsed_ms=int((time.time() - start) * 1000), error=f"Unsupported image extension for SMDI: {path.suffix}")
    try:
        power = parse_specular_power(specular_power)
        tool_path = Path(image_to_paa) if image_to_paa else None
        tga_path = smdi_output_path(path, False)
        paa_path = smdi_output_path(path, True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            converted = convert_smdi_pixels(_load_rgba(path, tool_path, tmp_root), power)
            if make_paa:
                height, width = converted.shape[:2]
                if width % PAA_BLOCK_SIZE or height % PAA_BLOCK_SIZE:
                    raise ValueError(f"PAA output needs width and height to be multiples of {PAA_BLOCK_SIZE}, but {path.name} is {width}x{height}.")
                if tool_path is None:
                    raise FileNotFoundError("ImageToPAA.exe path is missing or invalid.")
                temporary_tga = tmp_root / tga_path.name
                temporary_paa = tmp_root / paa_path.name
                Image.fromarray(converted, "RGBA").save(temporary_tga, format="TGA")
                _run_image_to_paa(tool_path, temporary_tga, temporary_paa)
                if not temporary_paa.exists():
                    raise RuntimeError(f"ImageToPAA.exe did not produce {paa_path.name}.")
                shutil.move(str(temporary_paa), str(paa_path))
                if tga_path.exists():
                    tga_path.unlink()
                outputs = [paa_path]
            else:
                temporary_tga = tmp_root / tga_path.name
                Image.fromarray(converted, "RGBA").save(temporary_tga, format="TGA")
                shutil.move(str(temporary_tga), str(tga_path))
                outputs = [tga_path]
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(True, input_path=path, outputs=outputs, processor="SMDI", elapsed_ms=elapsed, messages=[f"Generated {outputs[0].name} from {path.name} (specular power {power:g})."])
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, input_path=path, processor="SMDI", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}")


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _planned_outputs(path: Path, make_paa: bool) -> list[Path]:
    outputs = [smdi_output_path(path, make_paa)]
    if make_paa:
        outputs.append(smdi_output_path(path, False))
    return outputs


def _batch_conflict(path: Path, inputs: set[str], claimed: dict[str, Path], make_paa: bool) -> str:
    outputs = _planned_outputs(path, make_paa)
    keys = [_path_key(output) for output in outputs]
    for output, key in zip(outputs, keys):
        if key in inputs:
            return f"Output {output.name} would overwrite another input file in this batch."
        owner = claimed.get(key)
        if owner is not None:
            return f"Output {output.name} is already produced by {owner.name}."
    for key in keys:
        claimed[key] = path
    return ""


def convert_color_to_smdi_files(files: list[str | Path], specular_power: str | float = DEFAULT_SPECULAR_POWER, make_paa: bool = False, image_to_paa: str | Path | None = None, progress_callback: ProgressCallback | None = None) -> BatchResult:
    result = BatchResult()
    total = len(files)
    paths = [Path(item) for item in files]
    inputs = {_path_key(item) for item in paths}
    claimed: dict[str, Path] = {}
    for index, file_path in enumerate(paths, start=1):
        conflict = _batch_conflict(file_path, inputs, claimed, make_paa)
        if conflict:
            result.add(ProcessingResult(False, input_path=file_path, processor="SMDI", error=conflict))
        else:
            result.add(convert_color_to_smdi(file_path, specular_power, make_paa, image_to_paa))
        if progress_callback:
            progress_callback(index, total, file_path.name)
    return result
```

Three design points that are load-bearing:

- **Everything is written inside the temp directory and moved into place afterwards**, so a crash or a tool failure cannot leave a half-written `<stem>_smdi.tga` where a valid one used to be, and cannot leave tool garbage next to the user's textures.
- **`_batch_conflict` reserves both `<stem>_smdi.paa` and `<stem>_smdi.tga`** when `make_paa` is on, because the PAA branch also deletes the `.tga`. Without it, dropping `armor_co.tga` and `armor_smdi.tga` together would delete the second file before it is read, and dropping `armor_co.png` with `armor_ca.png` would make two inputs silently overwrite the same output.
- **`_run_image_to_paa` takes a required `output`**, so the destructive in-place mode can never be reached from this module.

- [ ] **Step 2: Run the processor tests**

Run:

```powershell
rtk python -m unittest tests.test_smdi -v
```

Expected: PASS for all 19 tests in `tests.test_smdi`.

- [ ] **Step 3: Commit**

```powershell
rtk git add src/dayz_texture_tool/processors/smdi.py tests/test_smdi.py
rtk git commit -m "feat: add smdi texture processor"
```

## Task 3: Persist The Specular Power Setting

**Files:**

- Modify: `src/dayz_texture_tool/settings.py`
- Modify: `tests/test_batch_settings.py`

- [ ] **Step 1: Add the failing settings test**

Add this method to the settings test class in `tests/test_batch_settings.py`:

```python
    def test_settings_persist_smdi_specular_power(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = AppSettings()
            settings.smdi_specular_power = 7.5

            save_settings(settings, path)
            loaded = load_settings(path)

            self.assertEqual(loaded.smdi_specular_power, 7.5)
```

If the file has no settings test class yet, add one as a new `unittest.TestCase` class and make sure the imports include:

```python
from dayz_texture_tool.settings import AppSettings, load_settings, save_settings
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
rtk python -m unittest tests.test_batch_settings -v
```

Expected: FAIL with `TypeError`/`AttributeError` for the missing `smdi_specular_power` field.

- [ ] **Step 3: Add the field**

In `src/dayz_texture_tool/settings.py`, append one field to `AppSettings` after `watermark_length`:

```python
    watermark_length: int = 0
    smdi_specular_power: float = 10.0
```

No other change is needed: `load_settings` merges `asdict(AppSettings())` with the JSON payload, and `save_settings` writes `asdict(settings)`.

- [ ] **Step 4: Run the settings tests**

Run:

```powershell
rtk python -m unittest tests.test_batch_settings -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add src/dayz_texture_tool/settings.py tests/test_batch_settings.py
rtk git commit -m "feat: persist smdi specular power"
```

## Task 4: Add The UI Strings

**Files:**

- Modify: `src/dayz_texture_tool/ui/i18n.py`

- [ ] **Step 1: Add the four keys to both languages**

In `src/dayz_texture_tool/ui/i18n.py`, add to the `zh` map next to the existing `watermark` keys:

```python
        "smdi": "SMDI",
        "drop_smdi_files": "拖拽颜色贴图到这里",
        "drop_smdi_files_hint": "支持 PAA、PNG、TGA、JPG、BMP、TIF；输出 <名字>_smdi.tga，勾选后打包为 PAA",
        "specular_power": "高光强度 (sp)",
```

and to the `en` map:

```python
        "smdi": "SMDI",
        "drop_smdi_files": "Drop color textures here",
        "drop_smdi_files_hint": "Supports PAA, PNG, TGA, JPG, BMP, TIF; writes <name>_smdi.tga and packs a PAA when checked",
        "specular_power": "Specular Power (sp)",
```

Reuse the existing `make_paa`, `select_files`, `clear_selected`, `process_selected`, `process_all`, `no_input`, `done`, `outputs`, `pending_status` and `status_ready` keys; do not add duplicates.

- [ ] **Step 2: Verify the file still parses and both languages have the keys**

Run:

```powershell
rtk python -c "import importlib.util; spec = importlib.util.spec_from_file_location('i18n_check', 'src/dayz_texture_tool/ui/i18n.py'); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); keys = ['smdi', 'drop_smdi_files', 'drop_smdi_files_hint', 'specular_power']; print({lang: [k for k in keys if k not in module.TEXTS[lang]] for lang in module.TEXTS})"
```

The file is loaded directly instead of via `from dayz_texture_tool.ui.i18n import TEXTS`, because that import runs `ui/__init__.py`, which imports `main_window`, which needs `customtkinter` (not installed here — see Known Environment Limits).

Expected: `{'zh': [], 'en': []}`.

- [ ] **Step 3: Commit**

```powershell
rtk git add src/dayz_texture_tool/ui/i18n.py
rtk git commit -m "feat: add smdi ui strings"
```

## Task 5: Add The SMDI Page

**Files:**

- Modify: `src/dayz_texture_tool/ui/main_window.py`

- [ ] **Step 1: Import the processor**

Modify the imports in `src/dayz_texture_tool/ui/main_window.py`:

```python
from dayz_texture_tool.processors.pbr2dayz import IMAGE_EXTENSIONS, convert_pbr_files
from dayz_texture_tool.processors.smdi import DEFAULT_SPECULAR_POWER, SUPPORTED_SMDI_EXTENSIONS, convert_color_to_smdi_files, parse_specular_power
from dayz_texture_tool.processors.watermark import SUPPORTED_WATERMARK_EXTENSIONS, add_watermark_files, detect_watermark_files
```

- [ ] **Step 2: Add pending state**

In `__init__`, after the watermark state:

```python
        self.watermark_pending_paths: list[Path] = []
        self.watermark_selected_paths: set[Path] = set()
        self.smdi_pending_paths: list[Path] = []
        self.smdi_selected_paths: set[Path] = set()
```

- [ ] **Step 3: Register the page and its builder**

**Edit the existing block at `src/dayz_texture_tool/ui/main_window.py:117-121` in place** — do not append a second copy of it, or `self.pages["settings"]` will be overwritten and the original settings frame orphaned:

```python
        self.game_tab = self._page("game")
        self.pbr_tab = self._page("pbr")
        self.watermark_tab = self._page("watermark")
        self.smdi_tab = self._page("smdi")
        self.settings_tab = self._page("settings")
        self._build_game_tab()
        self._build_pbr_tab()
        self._build_watermark_tab()
        self._build_smdi_tab()
        self._build_settings_tab()
```

and extend the navigation values in the same `_build` method:

```python
        self.widgets["nav"] = ctk.CTkSegmentedButton(header, values=["Game2PBR", "PBR2DayZ", "Watermark", "SMDI", "Settings"], command=self._show_page)
```

- [ ] **Step 4: Add the page builder**

Add this method next to `_build_watermark_tab`:

```python
    def _build_smdi_tab(self) -> None:
        self.smdi_tab.grid_columnconfigure(0, weight=7)
        self.smdi_tab.grid_columnconfigure(1, weight=3)
        self.smdi_tab.grid_rowconfigure(1, weight=1)
        controls = ctk.CTkFrame(self.smdi_tab)
        controls.grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="ew")
        controls.grid_columnconfigure(1, weight=1)
        self.widgets["smdi_specular_power_label"] = ctk.CTkLabel(controls)
        self.widgets["smdi_specular_power_label"].grid(row=0, column=0, padx=14, pady=14, sticky="w")
        self.widgets["smdi_specular_power"] = ctk.CTkEntry(controls, width=120)
        self.widgets["smdi_specular_power"].insert(0, f"{self.settings.smdi_specular_power:g}")
        self.widgets["smdi_specular_power"].grid(row=0, column=1, padx=8, pady=14, sticky="w")
        self.widgets["smdi_make_paa"] = ctk.CTkCheckBox(controls)
        self.widgets["smdi_make_paa"].grid(row=0, column=2, padx=8, pady=14)
        self.widgets["smdi_files_button"] = ctk.CTkButton(controls, command=self._select_smdi_files)
        self.widgets["smdi_files_button"].grid(row=0, column=3, padx=6, pady=14)
        self.widgets["smdi_drop"] = self._drop_area(self.smdi_tab, self._on_smdi_drop, "drop_smdi_files", "drop_smdi_files_hint")
        self.widgets["smdi_drop"].grid(row=1, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="nsew")
        self.widgets["smdi_pending"] = self._pending_panel(self.smdi_tab)
        self.widgets["smdi_pending"].grid(row=1, column=1, padx=(8, 14), pady=(8, 2), sticky="nsew")
        actions = ctk.CTkFrame(self.smdi_tab, fg_color="transparent")
        actions.grid(row=2, column=1, padx=(8, 14), pady=(2, 8), sticky="sew")
        for index in range(3):
            actions.grid_columnconfigure(index, weight=1)
        self.widgets["smdi_clear_selected_button"] = ctk.CTkButton(actions, command=lambda: self._clear_selected_pending("smdi"))
        self.widgets["smdi_clear_selected_button"].grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.widgets["smdi_selected_button"] = ctk.CTkButton(actions, command=self._start_smdi_selected)
        self.widgets["smdi_selected_button"].grid(row=0, column=1, padx=6, sticky="ew")
        self.widgets["smdi_start_button"] = ctk.CTkButton(actions, command=self._start_smdi_all)
        self.widgets["smdi_start_button"].grid(row=0, column=2, padx=(6, 0), sticky="ew")
        self.widgets["smdi_status"] = ctk.CTkLabel(self.smdi_tab, text_color="gray55", anchor="w")
        self.widgets["smdi_status"].grid(row=3, column=0, padx=(18, 8), pady=(4, 14), sticky="ew")
        self.widgets["smdi_progress"] = ctk.CTkProgressBar(self.smdi_tab, mode="determinate")
        self.widgets["smdi_progress"].set(0)
        self.widgets["smdi_progress"].grid(row=3, column=1, padx=(8, 18), pady=(4, 14), sticky="ew")
```

- [ ] **Step 5: Wire the page into navigation and language switching**

In `_show_page`, extend `page_map`:

```python
            "SMDI": "smdi",
            text(self.language, "smdi"): "smdi",
```

In `_apply_language`:

```python
        self.widgets["nav"].configure(values=[text(self.language, "game2pbr"), text(self.language, "pbr2dayz"), text(self.language, "watermark"), text(self.language, "smdi"), text(self.language, "settings")])
        nav_values = {"game": text(self.language, "game2pbr"), "pbr": text(self.language, "pbr2dayz"), "watermark": text(self.language, "watermark"), "smdi": text(self.language, "smdi"), "settings": text(self.language, "settings")}
        self.widgets["smdi_specular_power_label"].configure(text=text(self.language, "specular_power"))
        self.widgets["smdi_make_paa"].configure(text=text(self.language, "make_paa"))
        self.widgets["smdi_files_button"].configure(text=text(self.language, "select_files"))
        self.widgets["smdi_clear_selected_button"].configure(text=text(self.language, "clear_selected"))
        self.widgets["smdi_selected_button"].configure(text=text(self.language, "process_selected"))
        self.widgets["smdi_start_button"].configure(text=text(self.language, "process_all"))
        self._apply_drop_text("smdi_drop")
        self._render_pending("smdi_pending", self._smdi_pending_paths())
```

- [ ] **Step 6: Add selection, drop and pending helpers**

Add next to the watermark helpers:

```python
    def _smdi_pending_paths(self) -> list[Path]:
        return list(self.smdi_pending_paths)

    def _select_smdi_files(self) -> None:
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.tga *.tif *.tiff *.jpg *.jpeg *.bmp *.paa")])
        selected = self._unique_image_paths([Path(file) for file in files], SUPPORTED_SMDI_EXTENSIONS)
        if selected:
            self._set_pending_paths("smdi", selected)

    def _on_smdi_drop(self, event) -> None:
        paths = [Path(item) for item in self.tk.splitlist(event.data)]
        pending = []
        for path in paths:
            if path.is_dir():
                pending.extend(sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_SMDI_EXTENSIONS))
            elif path.is_file() and path.suffix.lower() in SUPPORTED_SMDI_EXTENSIONS:
                pending.append(path)
        if pending:
            self._set_pending_paths("smdi", self._unique_image_paths(pending, SUPPORTED_SMDI_EXTENSIONS))
```

Extend `_update_status_labels` with an `smdi` branch mirroring the watermark branch:

```python
        if "smdi_status" in self.widgets:
            smdi_total = len(self.smdi_pending_paths)
            smdi_selected = len(self.smdi_selected_paths)
            smdi_status = text(self.language, "pending_status").format(total=smdi_total, selected=smdi_selected) if smdi_total else text(self.language, "status_ready")
            self.widgets["smdi_status"].configure(text=smdi_status)
```

- [ ] **Step 7: Persist the specular power**

Add the save hook next to `_save_watermark_settings`. It reuses the processor's own validation, so `nan`, `inf` and negative values can never reach `settings.json`:

```python
    def _save_smdi_settings(self) -> None:
        if "smdi_specular_power" not in self.widgets:
            return
        try:
            self.settings.smdi_specular_power = parse_specular_power(self.widgets["smdi_specular_power"].get())
        except ValueError:
            self.settings.smdi_specular_power = DEFAULT_SPECULAR_POWER
```

Call `self._save_smdi_settings()` in `_toggle_language`, in `_save_settings` and in `_on_close`, next to the existing `self._save_watermark_settings()` calls.

- [ ] **Step 8: Surface per-file failure reasons**

`_show_result` only prints the ok/fail/skip counts, so a batch where every file failed (bad `sp`, missing `ImageToPAA.exe`, odd size) would report "0 ok, 3 failed" with no reason. Add an optional result hook to `_run_async` and make `_show_result` return the message it built:

```python
    def _run_async(self, work, status_key: str, progress_key: str, on_result=None) -> None:
        def runner():
            try:
                result = work()

                def finish():
                    message = self._show_result(status_key, progress_key, result)
                    if on_result is not None:
                        on_result(result, message)

                self.after(0, finish)
            except Exception:
                error = traceback.format_exc().splitlines()[-1]
                self.after(0, lambda: self._show_error(status_key, progress_key, error))
        threading.Thread(target=runner, daemon=True).start()
```

In `_show_result`, add `return message` as the final statement (it currently ends with `self.widgets[status_key].configure(text=message)`).

Then add the SMDI-side hook:

```python
    def _append_smdi_failure(self, result: BatchResult, message: str) -> None:
        reasons = [item.error for item in result.results if not item.success and item.error]
        if reasons:
            self.widgets["smdi_status"].configure(text=f"{message} {reasons[0]}")
```

`on_result` defaults to `None`, so every existing caller (`_start_game2pbr*`, `_start_pbr2dayz*`, `_start_watermark_*`) behaves exactly as before.

- [ ] **Step 9: Add the start actions**

Add next to the watermark start actions:

```python
    def _start_smdi_all(self) -> None:
        self._set_all_pending("smdi", True)
        self._start_smdi_selected()

    def _start_smdi_selected(self) -> None:
        selected_paths = self._selected_pending_paths("smdi")
        if not selected_paths:
            self.widgets["smdi_status"].configure(text=text(self.language, "no_input"))
            return
        self._save_smdi_settings()
        self.settings.image_to_paa = self.widgets["paa_path"].get()
        save_settings(self.settings)
        self._start_progress("smdi_progress")
        progress_callback = self._progress_callback("smdi_progress")
        specular_power = self.widgets["smdi_specular_power"].get()
        make_paa = bool(self.widgets["smdi_make_paa"].get())
        self._run_async(lambda: convert_color_to_smdi_files(selected_paths, specular_power=specular_power, make_paa=make_paa, image_to_paa=self.settings.image_to_paa, progress_callback=progress_callback), "smdi_status", "smdi_progress", self._append_smdi_failure)
```

Invalid `sp`, a missing `ImageToPAA.exe` and an unsupported size all become per-file `ProcessingResult` errors inside the worker, which `_append_smdi_failure` then shows next to the counts — no pre-flight duplication of that validation in the UI.

- [ ] **Step 10: Verify the module still imports and the new symbols resolve**

Run:

```powershell
rtk python -c "import ast, pathlib; ast.parse(pathlib.Path('src/dayz_texture_tool/ui/main_window.py').read_text(encoding='utf-8')); print('syntax ok')"
```

Expected: `syntax ok`. A full import needs `customtkinter`, which may not be installed here (see Known Environment Limits).

- [ ] **Step 11: Commit**

```powershell
rtk git add src/dayz_texture_tool/ui/main_window.py
rtk git commit -m "feat: add smdi page"
```

## Task 6: Add UI Tests For The SMDI Page

**Files:**

- Modify: `tests/test_ui_dragdrop.py`

- [ ] **Step 1: Extend `DummyApp`**

In `tests/test_ui_dragdrop.py`, add SMDI state to `DummyApp.__init__`:

```python
        self.smdi_pending_paths = []
        self.smdi_selected_paths = set()
```

add the settings value:

```python
            "smdi_specular_power": 10.0,
```

add the widgets:

```python
            "smdi_specular_power": type("Widget", (), {"get": lambda self: "10"})(),
            "smdi_make_paa": type("Widget", (), {"get": lambda self: 1})(),
            "smdi_status": type("Widget", (), {"configure": lambda self, **kwargs: None})(),
```

add the save hook stub next to `_save_watermark_settings`:

```python
    def _save_smdi_settings(self):
        pass

    def _smdi_pending_paths(self):
        return list(self.smdi_pending_paths)
```

and accept the new optional argument on the `_run_async` stub, otherwise `_start_smdi_selected` raises `TypeError`:

```python
    def _run_async(self, work, status_key, progress_key, on_result=None):
        self.work = work
```

- [ ] **Step 2: Add the SMDI tests**

Append to `UIDragDropTests`:

```python
    def test_smdi_process_selected_uses_selected_paths_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one_co.png"
            two = root / "two_co.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()

            main_window.DayZTextureToolApp._set_pending_paths(app, "smdi", [one, two])
            main_window.DayZTextureToolApp._select_pending_path(app, "smdi", two, False)

            with patch("dayz_texture_tool.ui.main_window.save_settings"), patch("dayz_texture_tool.ui.main_window.convert_color_to_smdi_files") as process:
                main_window.DayZTextureToolApp._start_smdi_selected(app)
                app.work()

            process.assert_called_once()
            self.assertEqual(process.call_args.args[0], [one])
            self.assertEqual(process.call_args.kwargs["specular_power"], "10")
            self.assertEqual(process.call_args.kwargs["make_paa"], True)
            self.assertEqual(process.call_args.kwargs["image_to_paa"], "D:/tools/ImageToPAA.exe")

    def test_smdi_drop_accepts_paa_and_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paa = root / "armor_co.paa"
            png = root / "armor_ca.png"
            other = root / "notes.txt"
            for path in (paa, png, other):
                path.write_bytes(b"x")
            app = DummyApp()

            main_window.DayZTextureToolApp._on_smdi_drop(app, DummyEvent(f"{paa}|{png}|{other}"))

            self.assertEqual(app.smdi_pending_paths, [paa, png])
            self.assertEqual(app.smdi_selected_paths, {paa, png})
```

- [ ] **Step 3: Run the UI tests if the environment supports them**

Run:

```powershell
rtk python -m unittest tests.test_ui_dragdrop -v
```

If `customtkinter` is not installed this fails with `ModuleNotFoundError: No module named 'customtkinter'` **before any test runs** — that is the pre-existing environmental failure described in Known Environment Limits. In that case record the result as **not executed** and do not claim these tests pass. Note that `tests/test_smdi.py` does **not** cover these two cases: nothing there calls `_start_smdi_selected` or `_on_smdi_drop`, so a green `tests.test_smdi` is not evidence that the page wiring works.

- [ ] **Step 4: Commit**

```powershell
rtk git add tests/test_ui_dragdrop.py
rtk git commit -m "test: cover smdi page wiring"
```

## Task 7: Final Verification

**Files:**

- All changed files
- CodeGraph index

- [ ] **Step 1: Run the runnable tests**

Run:

```powershell
rtk python -m unittest tests.test_smdi tests.test_batch_settings -v
```

Expected: all PASS.

- [ ] **Step 2: Run the full suite and compare against the baseline**

Run:

```powershell
rtk python -m unittest discover tests 2>&1 | tail -20
```

Expected: the same 3 pre-existing environmental problems as the baseline (`test_ui_dragdrop` import error, two `blind-watermark` failures) and **no new failure**. Report the raw counts; do not describe the suite as passing.

- [ ] **Step 3: Inspect the diff**

Run:

```powershell
rtk git status --short
rtk git diff --stat HEAD~5
```

Expected: changes limited to `processors/smdi.py`, `settings.py`, `ui/i18n.py`, `ui/main_window.py`, `tests/test_smdi.py`, `tests/test_batch_settings.py`, `tests/test_ui_dragdrop.py`, plus this plan (which is untracked, so it only shows in `git status`, not in `git diff`).

- [ ] **Step 4: Sync the CodeGraph index**

Run:

```powershell
rtk codegraph sync
rtk codegraph status
```

Expected: the index reports the changed files and `[OK] Index is up to date`.

- [ ] **Step 5: Manual smoke test (only where the real tool is reachable)**

This is the one check that cannot be automated in this environment, because it needs the real `ImageToPAA.exe` and a real color texture. Run the app, open the `SMDI` page, drop one `*_co.paa`, keep `sp = 10`, and process it twice: once without `Output PAA` and once with it. Then confirm:

- Without `Output PAA`: `<stem>_smdi.tga` appears next to the input and its R channel equals `255` minus the **source** texture's green channel (`255 - G_source`, not the output's green channel).
- With `Output PAA`: `<stem>_smdi.paa` appears, no `.tga` is left behind, and decoding that PAA with `ImageToPAA.exe` shows `R = 255`, `A = 255` (fact 3), with G/B within a step or two of the TGA (fact 6 — DXT1 is lossy, so exact equality is *not* expected).
- Both runs must use a source whose width and height are multiples of 4; a 1000x563 screenshot is expected to fail with the readable "multiples of 4" error, which is the correct behaviour, not a bug.

If the real tool is unavailable, say so explicitly instead of claiming the smoke test ran.

## Self-Review

- **Spec coverage:** dedicated page (Q1), TGA + optional PAA output (Q2), existing app (Q3), editable persisted `sp` (Q4), `_co`/`_ca` stripping (Q5), no leftover TGA when packing — including a stale one from an earlier run (Q6), `.paa` + common images as input (Q7), silent overwrite (Q8), `R = 1-G` in the TGA (Q9), plan-first review (Q10). Each maps to a task above.
- **Placeholder scan:** no unresolved placeholders; every implementation step names the file and gives the concrete code.
- **Type consistency:** `specular_power` (str|float in, float out), `make_paa`, `image_to_paa`, `smdi_output_stem`, `smdi_output_path`, `convert_smdi_pixels`, `convert_color_to_smdi`, `convert_color_to_smdi_files`, `parse_specular_power` and `smdi_specular_power` are spelled identically in the processor, the UI, the settings and the tests.
- **Scope check:** no new dependency, no change to `PBR2DayZ`'s existing SMDI path, no refactor of the duplicated `ImageToPAA` subprocess helper. That duplication is deliberate and its justification is narrow: `processors/watermark.py:69-78` already takes an explicit destination and raises, so `smdi.py`'s copy could in principle be replaced by a shared helper — but factoring one out means editing `processors/watermark.py`, a working module whose PAA path cannot be exercised in this environment (`blind-watermark` is not installed). That refactor is out of scope here; the new copy differs by making `output` required and by not offering the skip-and-continue behaviour of `processors/pbr2dayz.py:219-229`.
- **Deliberate deviations from the first draft, after review:** the `*_smdi.*` rule was documented against the wrong filename (fact 4); the multiple-of-4 constraint was missing (fact 5); an existing `_smdi.tga` was not removed in the PAA path (Q6); batch output collisions could silently overwrite an input or another file's output; per-file failure reasons never reached the status label; and the TGA was written straight into the output folder instead of through the temp directory.
- **Risk called out:** the R channel of a shipped SMDI PAA is always 255 regardless of what this feature writes, so any future "the R channel is wrong" report should be checked against fact 3 first. Likewise, a "the PAA colours are slightly off" report is DXT1 compression (fact 6), not a formula bug.

## Implementation Notes

Deviations and plan defects found while implementing this plan.

- **Task 3 (order):** the `smdi_specular_power` field was added to `settings.py` before its test was written, so `test_settings_persist_smdi_specular_power` has no red-run evidence. The substitute evidence is a probe: the field exists, defaults to `10.0`, and a legacy `settings.json` containing only `{"language": "en"}` loads with `smdi_specular_power == 10.0`.
- **Task 4 Step 2 (command was wrong):** `from dayz_texture_tool.ui.i18n import TEXTS` runs `ui/__init__.py`, which imports `main_window`, which raises `RuntimeError: customtkinter is required. Install requirements.txt first.` The step now loads `src/dayz_texture_tool/ui/i18n.py` directly with `importlib.util.spec_from_file_location`.
- **Task 5 Step 8 (signature):** `_show_result` is annotated `-> str`, not `-> None`. The step adds `return message`, which a `-> None` annotation would reject. `on_result` is left unannotated, matching the existing unannotated `work` parameter of `_run_async`.
- **Task 5 verification:** `pyright src/dayz_texture_tool/ui/main_window.py` reports 128 errors against 114 at `HEAD`. Every added one belongs to the file's pre-existing pattern — `self.widgets` is declared `dict[str, object]`, so each `.configure()`/`.set()`/`.grid()` is `reportAttributeAccessIssue` — plus one `list[Path]` vs `list[str | Path]` message of exactly the kind already reported four times at `HEAD` (`main_window.py:824`, `:854`, `:867`, `:879`, once per existing processor call). No new class of error is introduced, and `ast.parse` succeeds.
- **Task 6 (cannot run here):** `tests/test_ui_dragdrop.py` imports `main_window`, so without `customtkinter` installed the UI tests cannot be executed in this environment. They are written, not verified — see Known Environment Limits.
- **Task 7 Step 5 (processor level, real tool — the Tkinter UI itself was NOT exercised):** the committed processor was driven end-to-end against the real `ImageToPAA.exe` on an 8x8 source of `[200, 128, 64, 255]` with `sp = 10`. Without `Output PAA` the result was `armor_smdi.tga` with R/G/B/A `[127, 41, 64, 255]`, equal to the `convert_smdi_pixels` expectation and to the pre-verified test vector; `R = 255 - G_source = 127` holds. With `Output PAA` the result was `armor_smdi.paa`, no `.tga` was left behind, and decoding that PAA back through `ImageToPAA.exe` gave R/G/B/A `[255, 42, 63, 255]` — R and A forced to 255 (fact 3) with G/B one step from the TGA (fact 6). A 3x3 source with `Output PAA` failed with `ValueError: PAA output needs width and height to be multiples of 4, but odd_co.png is 3x3.` and wrote nothing. Because `customtkinter` is missing, no click-through of the new page was possible; the page's wiring is covered only by `tests/test_ui_dragdrop.py`, which could not be executed.
- **Task 7 Step 2 (full suite):** `rtk python -m unittest discover tests` → `Ran 70 tests`, `FAILED (failures=2, errors=1)`. That is the documented baseline (one `test_ui_dragdrop` import error from the missing `customtkinter`, two `blind-watermark` failures) and no new failure; the runnable subset `tests.test_smdi tests.test_batch_settings` is 29 tests, `OK`.
- **Task 7 Step 3 (diff):** changes are limited to `processors/smdi.py`, `settings.py`, `ui/i18n.py`, `ui/main_window.py`, `tests/test_smdi.py`, `tests/test_batch_settings.py`, `tests/test_ui_dragdrop.py` and this plan. This plan is tracked (committed), so unlike the step's expectation it *does* appear in `git diff --stat`; use `HEAD~6` to span all six commits.
