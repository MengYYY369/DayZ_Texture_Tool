# PAA Watermark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add blind-watermark support to PBR2DayZ and add a dedicated Watermark page for adding and detecting watermarks.

**Architecture:** Keep watermark encoding/decoding in a focused processor module so the UI only collects inputs and displays results. PBR2DayZ gets a single "add watermark" switch that reuses settings, while the new Watermark page provides standalone add/detect actions. Existing `.paa` creation still goes through `ImageToPAA.exe`; direct `.paa` watermark detection/addition is rejected with a clear message until a PAA decode tool is configured because `blind_watermark` only accepts normal image files.

**Tech Stack:** Python 3.10, customtkinter, Pillow, numpy, blind-watermark, unittest, CodeGraph CLI.

---

## File Structure

- Modify: `pyproject.toml`
  - Add `blind-watermark` runtime dependency.
- Modify: `requirements.txt`
  - Add `blind-watermark` for non-PEP 621 installs.
- Modify: `src/dayz_texture_tool/models.py`
  - Add optional metadata to `ProcessingResult` so watermark bit length and extracted text can be reported without parsing messages.
- Create: `src/dayz_texture_tool/processors/watermark.py`
  - Own all blind-watermark operations, input validation, batch add/detect helpers, and the `.paa` unsupported guard.
- Modify: `src/dayz_texture_tool/processors/pbr2dayz.py`
  - Add optional watermark parameters to PBR conversion functions.
  - Apply watermark after TGA generation and before optional PAA conversion.
- Modify: `src/dayz_texture_tool/settings.py`
  - Persist watermark content, password, and last bit length.
- Modify: `src/dayz_texture_tool/ui/main_window.py`
  - Add top navigation page `Watermark`.
  - Add PBR2DayZ "add watermark" checkbox only.
  - Add Watermark page selection/add/detect controls.
  - Wire settings fields and async actions.
- Modify: `src/dayz_texture_tool/ui/i18n.py`
  - Add labels/status strings. Preserve the file's current encoding; do not re-encode the whole file.
- Create: `tests/test_watermark.py`
  - Unit tests for processor behavior with `blind_watermark` mocked.
- Modify: `tests/test_pbr2dayz.py`
  - Test PBR2DayZ invokes watermark before PAA conversion.
- Modify: `tests/test_ui_dragdrop.py`
  - Test UI wiring for PBR watermark flag and Watermark page actions using existing dummy app style.

## Success Criteria

- PBR2DayZ has one new checkbox: `添加水印`.
- Enabling that checkbox applies the settings watermark to generated TGA files before `ImageToPAA.exe` runs.
- Top navigation includes `Watermark` / `水印`.
- Watermark page can select supported image files and run standalone add/detect actions.
- Watermark page rejects `.paa` files with an explicit unsupported message unless a later task adds a decode tool.
- Settings page persists watermark content, password, and last bit length.
- Unit tests pass.
- CodeGraph index is synced after code changes.

## Task 1: Add Dependency Entries

**Files:**
- Modify: `pyproject.toml`
- Modify: `requirements.txt`

- [ ] **Step 1: Write dependency expectation check**

Run:

```powershell
rtk powershell -NoProfile -Command "Select-String -Path pyproject.toml,requirements.txt -Pattern 'blind-watermark|blind_watermark'"
```

Expected before implementation: no matching dependency line.

- [ ] **Step 2: Add dependency to `pyproject.toml`**

Add `"blind-watermark>=0.4.4",` to the `[project].dependencies` list near the image stack:

```toml
dependencies = [
    "customtkinter>=5.2.2",
    "tkinterdnd2>=0.4.2",
    "Pillow>=10.0.0",
    "numpy>=1.24.0",
    "blind-watermark>=0.4.4",
]
```

- [ ] **Step 3: Add dependency to `requirements.txt`**

Ensure the file contains:

```text
customtkinter>=5.2.2
tkinterdnd2>=0.4.2
Pillow>=10.0.0
numpy>=1.24.0
blind-watermark>=0.4.4
```

- [ ] **Step 4: Verify dependency entries**

Run:

```powershell
rtk powershell -NoProfile -Command "Select-String -Path pyproject.toml,requirements.txt -Pattern 'blind-watermark'"
```

Expected: one match in `pyproject.toml` and one match in `requirements.txt`.

- [ ] **Step 5: Commit**

```powershell
rtk git add pyproject.toml requirements.txt
rtk git commit -m "build: add blind watermark dependency"
```

## Task 2: Add Watermark Processor Tests

**Files:**
- Create: `tests/test_watermark.py`
- Later implementation target: `src/dayz_texture_tool/processors/watermark.py`

- [ ] **Step 1: Create failing tests**

Create `tests/test_watermark.py`:

```python
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
            image = root / "source.tga"
            output = root / "source_watermarked.tga"
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


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
rtk python -m unittest tests.test_watermark -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'dayz_texture_tool.processors.watermark'`.

- [ ] **Step 3: Do not implement yet**

Stop after seeing the failure. Implementation happens in Task 3.

## Task 3: Implement Watermark Processor

**Files:**
- Create: `src/dayz_texture_tool/processors/watermark.py`
- Modify: `src/dayz_texture_tool/models.py`
- Test: `tests/test_watermark.py`

- [ ] **Step 1: Add metadata to `ProcessingResult`**

Modify `src/dayz_texture_tool/models.py`:

```python
@dataclass
class ProcessingResult:
    success: bool
    input_path: Path | None = None
    outputs: list[Path] = field(default_factory=list)
    processor: str = ""
    elapsed_ms: int = 0
    error: str = ""
    messages: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)
```

- [ ] **Step 2: Create processor implementation**

Create `src/dayz_texture_tool/processors/watermark.py`:

```python
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from blind_watermark import WaterMark

from dayz_texture_tool.models import BatchResult, ProcessingResult


SUPPORTED_WATERMARK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".tga"}

ProgressCallback = Callable[[int, int, str], None]


def _password(value: str | int) -> int:
    text = str(value).strip()
    if not text:
        return 1
    try:
        return int(text)
    except ValueError as exc:
        raise ValueError("Watermark password must be an integer.") from exc


def _output_path(path: Path, output_path: str | Path | None = None) -> Path:
    if output_path is not None:
        return Path(output_path)
    return path.with_name(f"{path.stem}_watermarked{path.suffix}")


def _unsupported_paa(path: Path) -> ProcessingResult | None:
    if path.suffix.lower() == ".paa":
        return ProcessingResult(
            False,
            input_path=path,
            processor="Watermark",
            error="PAA watermarking requires a PAA decode tool before blind_watermark can process it.",
        )
    return None


def _unsupported_image(path: Path) -> ProcessingResult | None:
    if path.suffix.lower() not in SUPPORTED_WATERMARK_EXTENSIONS:
        return ProcessingResult(
            False,
            input_path=path,
            processor="Watermark",
            error=f"Unsupported image extension for watermark: {path.suffix}",
        )
    return None


def add_watermark(input_path: str | Path, content: str, password: str | int = 1, output_path: str | Path | None = None) -> ProcessingResult:
    start = time.time()
    path = Path(input_path)
    if not content:
        return ProcessingResult(False, input_path=path, processor="Watermark", error="Watermark content is empty.")
    unsupported = _unsupported_paa(path) or _unsupported_image(path)
    if unsupported is not None:
        return unsupported
    try:
        pwd = _password(password)
        output = _output_path(path, output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        bwm = WaterMark(password_img=pwd, password_wm=pwd)
        bwm.read_img(str(path))
        bwm.read_wm(content, mode="str")
        bwm.embed(str(output))
        length = len(bwm.wm_bit)
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(
            True,
            input_path=path,
            outputs=[output],
            processor="Watermark",
            elapsed_ms=elapsed,
            messages=[f"Watermark embedded in {output.name}; wm_bit length: {length}."],
            metadata={"watermark_length": length},
        )
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, input_path=path, processor="Watermark", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}")


def add_watermark_in_place(input_path: str | Path, content: str, password: str | int = 1) -> ProcessingResult:
    path = Path(input_path)
    temp_output = path.with_name(f"{path.stem}.__watermark_tmp__{path.suffix}")
    result = add_watermark(path, content, password, temp_output)
    if not result.success:
        return result
    temp_output.replace(path)
    result.outputs = [path]
    result.messages = [f"Watermark embedded in {path.name}; wm_bit length: {result.metadata['watermark_length']}."]
    return result


def detect_watermark(input_path: str | Path, password: str | int = 1, watermark_length: int = 0) -> ProcessingResult:
    start = time.time()
    path = Path(input_path)
    if watermark_length <= 0:
        return ProcessingResult(False, input_path=path, processor="Watermark", error="Watermark length must be greater than 0.")
    unsupported = _unsupported_paa(path) or _unsupported_image(path)
    if unsupported is not None:
        return unsupported
    try:
        pwd = _password(password)
        bwm = WaterMark(password_img=pwd, password_wm=pwd)
        extracted = bwm.extract(str(path), wm_shape=watermark_length, mode="str")
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(
            True,
            input_path=path,
            processor="Watermark",
            elapsed_ms=elapsed,
            messages=[f"Extracted watermark from {path.name}: {extracted}"],
            metadata={"watermark_text": extracted},
        )
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, input_path=path, processor="Watermark", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}")


def add_watermark_files(files: list[str | Path], content: str, password: str | int = 1, progress_callback: ProgressCallback | None = None) -> BatchResult:
    result = BatchResult()
    total = len(files)
    for index, file_path in enumerate(files, start=1):
        item = add_watermark(file_path, content, password)
        result.add(item)
        if progress_callback:
            progress_callback(index, total, Path(file_path).name)
    return result


def detect_watermark_files(files: list[str | Path], password: str | int = 1, watermark_length: int = 0, progress_callback: ProgressCallback | None = None) -> BatchResult:
    result = BatchResult()
    total = len(files)
    for index, file_path in enumerate(files, start=1):
        item = detect_watermark(file_path, password, watermark_length)
        result.add(item)
        if progress_callback:
            progress_callback(index, total, Path(file_path).name)
    return result
```

- [ ] **Step 3: Run processor tests**

Run:

```powershell
rtk python -m unittest tests.test_watermark -v
```

Expected: PASS for all tests in `tests.test_watermark`.

- [ ] **Step 4: Commit**

```powershell
rtk git add src/dayz_texture_tool/models.py src/dayz_texture_tool/processors/watermark.py tests/test_watermark.py
rtk git commit -m "feat: add watermark processor"
```

## Task 4: Wire Watermark Into PBR2DayZ Processor

**Files:**
- Modify: `src/dayz_texture_tool/processors/pbr2dayz.py`
- Modify: `tests/test_pbr2dayz.py`

- [ ] **Step 1: Add failing PBR2DayZ test**

Append this test to `PBR2DayZTests` in `tests/test_pbr2dayz.py`:

```python
    def test_convert_pbr_folder_embeds_watermark_before_paa_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "TestMat_BaseColor.png"
            save_rgb(base, [100, 90, 80])
            image_to_paa = root / "ImageToPAA.exe"
            image_to_paa.write_text("stub", encoding="utf-8")
            calls = []

            def fake_watermark(path, content, password):
                calls.append(("watermark", Path(path).name, content, password))
                return pbr2dayz.ProcessingResult(True, input_path=Path(path), outputs=[Path(path)], processor="Watermark", metadata={"watermark_length": 12})

            def fake_paa(outputs, image_to_paa_path, messages):
                calls.append(("paa", [Path(output).name for output in outputs]))

            with patch("dayz_texture_tool.processors.pbr2dayz.add_watermark_in_place", fake_watermark):
                with patch("dayz_texture_tool.processors.pbr2dayz._run_image_to_paa", fake_paa):
                    result = convert_pbr_folder(
                        root,
                        make_paa=True,
                        image_to_paa=image_to_paa,
                        add_watermark=True,
                        watermark_content="secret",
                        watermark_password="9",
                    )

            self.assertTrue(result.success)
            self.assertEqual(calls[0], ("watermark", f"{root.name}_co.tga", "secret", "9"))
            self.assertEqual(calls[1], ("paa", [f"{root.name}_co.tga"]))
            self.assertEqual(result.results[0].metadata["watermark_length"], 12)
```

- [ ] **Step 2: Run the new test to verify it fails**

Run:

```powershell
rtk python -m unittest tests.test_pbr2dayz.PBR2DayZTests.test_convert_pbr_folder_embeds_watermark_before_paa_conversion -v
```

Expected: FAIL with `TypeError` for unexpected keyword argument `add_watermark`.

- [ ] **Step 3: Import watermark helper**

Modify imports in `src/dayz_texture_tool/processors/pbr2dayz.py`:

```python
from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.processors.watermark import add_watermark_in_place
from dayz_texture_tool.recycle import move_to_recycle_bin
```

- [ ] **Step 4: Add helper function**

Add near `_delete_tga_outputs_with_paa`:

```python
def _add_watermarks(outputs: list[Path], content: str, password: str | int, messages: list[str]) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for output in outputs:
        result = add_watermark_in_place(output, content, password)
        messages.extend(result.messages)
        if not result.success:
            raise RuntimeError(result.error)
        if "watermark_length" in result.metadata:
            metadata["watermark_length"] = result.metadata["watermark_length"]
    return metadata
```

- [ ] **Step 5: Extend `convert_pbr_group` signature and body**

Change the signature to:

```python
def convert_pbr_group(group: PBRGroup, normal_type: str = "directx", resolution: str = "auto", co_mode: str = "basecolor", specular: float = 0.75, glossiness: float = 1.0, make_paa: bool = False, image_to_paa: str | Path | None = None, delete_source: bool = False, output_suffixes: dict[str, str] | None = None, add_watermark: bool = False, watermark_content: str = "", watermark_password: str | int = 1) -> ProcessingResult:
```

Inside the `try` block, initialize metadata after `messages`:

```python
        metadata: dict[str, object] = {}
```

After all TGA outputs are appended and before `if make_paa and outputs:`:

```python
        if add_watermark and outputs:
            metadata.update(_add_watermarks(outputs, watermark_content, watermark_password, messages))
```

Change the successful return to include metadata:

```python
        return ProcessingResult(True, outputs=outputs, processor="PBR2DayZ", elapsed_ms=elapsed, messages=messages, metadata=metadata)
```

Change the exception return to include metadata:

```python
        return ProcessingResult(False, processor="PBR2DayZ", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}", messages=messages, metadata=metadata if "metadata" in locals() else {})
```

- [ ] **Step 6: Extend folder and file conversion signatures**

Change `convert_pbr_folder` and `convert_pbr_files` signatures to include:

```python
add_watermark: bool = False, watermark_content: str = "", watermark_password: str | int = 1
```

Pass those values into each `convert_pbr_group` call:

```python
result.add(convert_pbr_group(group, normal_type, resolution, co_mode, specular, glossiness, make_paa, image_to_paa, delete_source, output_suffixes, add_watermark, watermark_content, watermark_password))
```

- [ ] **Step 7: Run focused PBR2DayZ test**

Run:

```powershell
rtk python -m unittest tests.test_pbr2dayz.PBR2DayZTests.test_convert_pbr_folder_embeds_watermark_before_paa_conversion -v
```

Expected: PASS.

- [ ] **Step 8: Run full PBR2DayZ tests**

Run:

```powershell
rtk python -m unittest tests.test_pbr2dayz -v
```

Expected: PASS.

- [ ] **Step 9: Commit**

```powershell
rtk git add src/dayz_texture_tool/processors/pbr2dayz.py tests/test_pbr2dayz.py
rtk git commit -m "feat: watermark pbr2dayz outputs"
```

## Task 5: Persist Watermark Settings

**Files:**
- Modify: `src/dayz_texture_tool/settings.py`
- Modify: `tests/test_batch_settings.py`

- [ ] **Step 1: Add failing settings test**

Add this test to the existing settings test class in `tests/test_batch_settings.py`; if the file has no settings class, add it as a new `unittest.TestCase` class:

```python
    def test_settings_persist_watermark_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            settings = AppSettings()
            settings.watermark_content = "secret"
            settings.watermark_password = "9"
            settings.watermark_length = 12

            save_settings(settings, path)
            loaded = load_settings(path)

            self.assertEqual(loaded.watermark_content, "secret")
            self.assertEqual(loaded.watermark_password, "9")
            self.assertEqual(loaded.watermark_length, 12)
```

Ensure imports include:

```python
from dayz_texture_tool.settings import AppSettings, load_settings, save_settings
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
rtk python -m unittest tests.test_batch_settings -v
```

Expected: FAIL with `AttributeError` for missing watermark settings fields.

- [ ] **Step 3: Add fields to `AppSettings`**

Modify `src/dayz_texture_tool/settings.py`:

```python
@dataclass
class AppSettings:
    image_to_paa: str = r"D:\steam\steamapps\common\DayZ Tools\Bin\ImageToPAA\ImageToPAA.exe"
    language: str = "zh"
    game_suffixes: dict[str, list[str]] = field(default_factory=lambda: {key: list(value) for key, value in DEFAULT_GAME_SUFFIXES.items()})
    game_output_suffixes: dict[str, dict[str, str]] = field(default_factory=lambda: {key: dict(value) for key, value in DEFAULT_GAME_OUTPUT_SUFFIXES.items()})
    pbr_suffixes: dict[str, list[str]] = field(default_factory=lambda: {key: list(value) for key, value in DEFAULT_PBR_SUFFIXES.items()})
    pbr_output_suffixes: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PBR_OUTPUT_SUFFIXES))
    pbr_prefix_mode: str = "auto"
    pbr_custom_prefix: str = ""
    game_match_mode: str = "exact"
    pbr_match_mode: str = "fuzzy"
    watermark_content: str = ""
    watermark_password: str = "1"
    watermark_length: int = 0
```

- [ ] **Step 4: Run settings tests**

Run:

```powershell
rtk python -m unittest tests.test_batch_settings -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
rtk git add src/dayz_texture_tool/settings.py tests/test_batch_settings.py
rtk git commit -m "feat: persist watermark settings"
```

## Task 6: Add UI Tests For PBR2DayZ Watermark Flag

**Files:**
- Modify: `tests/test_ui_dragdrop.py`
- Later implementation target: `src/dayz_texture_tool/ui/main_window.py`

- [ ] **Step 1: Extend `DummyApp` settings and widgets**

In `tests/test_ui_dragdrop.py`, update dummy settings:

```python
            "watermark_content": "secret",
            "watermark_password": "9",
            "watermark_length": 12,
```

Add a watermark checkbox widget:

```python
            "pbr_add_watermark": type("Widget", (), {"get": lambda self: 1})(),
```

- [ ] **Step 2: Update existing PBR selected test expectation**

In `test_pbr_process_selected_uses_selected_paths_only`, add:

```python
            self.assertEqual(process.call_args.kwargs["add_watermark"], True)
            self.assertEqual(process.call_args.kwargs["watermark_content"], "secret")
            self.assertEqual(process.call_args.kwargs["watermark_password"], "9")
```

- [ ] **Step 3: Run UI test to verify it fails**

Run:

```powershell
rtk python -m unittest tests.test_ui_dragdrop.UIDragDropTests.test_pbr_process_selected_uses_selected_paths_only -v
```

Expected: FAIL because `_start_pbr2dayz_selected` does not pass watermark keyword arguments.

- [ ] **Step 4: Do not implement yet**

Stop after seeing the failure. UI implementation happens in Task 7.

## Task 7: Add Navigation, PBR Checkbox, Watermark Page, And Settings Fields

**Files:**
- Modify: `src/dayz_texture_tool/ui/main_window.py`
- Modify: `src/dayz_texture_tool/ui/i18n.py`
- Modify: `tests/test_ui_dragdrop.py`

- [ ] **Step 1: Update imports**

Modify imports in `src/dayz_texture_tool/ui/main_window.py`:

```python
from dayz_texture_tool.processors.watermark import SUPPORTED_WATERMARK_EXTENSIONS, add_watermark_files, detect_watermark_files
```

- [ ] **Step 2: Add state in `__init__`**

Add after PBR state:

```python
        self.watermark_pending_paths: list[Path] = []
        self.watermark_selected_paths: set[Path] = set()
```

- [ ] **Step 3: Add nav page**

In `_build`, change nav default values:

```python
        self.widgets["nav"] = ctk.CTkSegmentedButton(header, values=["Game2PBR", "PBR2DayZ", "Watermark", "Settings"], command=self._show_page)
```

Create the page:

```python
        self.watermark_tab = self._page("watermark")
```

Build it before settings:

```python
        self._build_watermark_tab()
        self._build_settings_tab()
```

- [ ] **Step 4: Add PBR checkbox**

In `_build_pbr_tab`, after `make_paa`:

```python
        self.widgets["pbr_add_watermark"] = ctk.CTkCheckBox(controls)
        self.widgets["pbr_add_watermark"].grid(row=0, column=5, padx=10, pady=14)
        self.widgets["pbr_delete_source"] = ctk.CTkCheckBox(controls)
        self.widgets["pbr_delete_source"].grid(row=0, column=6, padx=10, pady=14)
```

Shift the following `pbr_folder_button`, `pbr_files_button`, and `pbr_match_mode` columns by one.

- [ ] **Step 5: Add Watermark page builder**

Add this method to `DayZTextureToolApp`:

```python
    def _build_watermark_tab(self) -> None:
        self.watermark_tab.grid_columnconfigure(0, weight=7)
        self.watermark_tab.grid_columnconfigure(1, weight=3)
        self.watermark_tab.grid_rowconfigure(1, weight=1)
        controls = ctk.CTkFrame(self.watermark_tab)
        controls.grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="ew")
        controls.grid_columnconfigure(1, weight=1)
        self.widgets["watermark_length_label"] = ctk.CTkLabel(controls)
        self.widgets["watermark_length_label"].grid(row=0, column=0, padx=14, pady=14, sticky="w")
        self.widgets["watermark_length"] = ctk.CTkEntry(controls, width=120)
        self.widgets["watermark_length"].insert(0, str(self.settings.watermark_length))
        self.widgets["watermark_length"].grid(row=0, column=1, padx=8, pady=14, sticky="w")
        self.widgets["watermark_files_button"] = ctk.CTkButton(controls, command=self._select_watermark_files)
        self.widgets["watermark_files_button"].grid(row=0, column=2, padx=6, pady=14)

        self.widgets["watermark_drop"] = self._drop_area(self.watermark_tab, self._on_watermark_drop, "drop_watermark_files", "drop_watermark_files_hint")
        self.widgets["watermark_drop"].grid(row=1, column=0, rowspan=2, padx=(14, 8), pady=8, sticky="nsew")
        self.widgets["watermark_pending"] = self._pending_panel(self.watermark_tab)
        self.widgets["watermark_pending"].grid(row=1, column=1, padx=(8, 14), pady=(8, 2), sticky="nsew")

        actions = ctk.CTkFrame(self.watermark_tab, fg_color="transparent")
        actions.grid(row=2, column=1, padx=(8, 14), pady=(2, 8), sticky="sew")
        for index in range(3):
            actions.grid_columnconfigure(index, weight=1)
        self.widgets["watermark_clear_selected_button"] = ctk.CTkButton(actions, command=lambda: self._clear_selected_pending("watermark"))
        self.widgets["watermark_clear_selected_button"].grid(row=0, column=0, padx=(0, 6), sticky="ew")
        self.widgets["watermark_add_button"] = ctk.CTkButton(actions, command=self._start_watermark_add_selected)
        self.widgets["watermark_add_button"].grid(row=0, column=1, padx=6, sticky="ew")
        self.widgets["watermark_detect_button"] = ctk.CTkButton(actions, command=self._start_watermark_detect_selected)
        self.widgets["watermark_detect_button"].grid(row=0, column=2, padx=(6, 0), sticky="ew")

        self.widgets["watermark_status"] = ctk.CTkLabel(self.watermark_tab, text_color="gray55", anchor="w")
        self.widgets["watermark_status"].grid(row=3, column=0, padx=(18, 8), pady=(4, 14), sticky="ew")
        self.widgets["watermark_progress"] = ctk.CTkProgressBar(self.watermark_tab, mode="determinate")
        self.widgets["watermark_progress"].set(0)
        self.widgets["watermark_progress"].grid(row=3, column=1, padx=(8, 18), pady=(4, 14), sticky="ew")
```

- [ ] **Step 6: Include watermark page in navigation**

In `_show_page`, add:

```python
            "Watermark": "watermark",
            text(self.language, "watermark"): "watermark",
```

Update fallback display map handling so `watermark` can be selected.

In `_apply_language`, configure nav values:

```python
        self.widgets["nav"].configure(values=[text(self.language, "game2pbr"), text(self.language, "pbr2dayz"), text(self.language, "watermark"), text(self.language, "settings")])
        nav_values = {"game": text(self.language, "game2pbr"), "pbr": text(self.language, "pbr2dayz"), "watermark": text(self.language, "watermark"), "settings": text(self.language, "settings")}
```

- [ ] **Step 7: Add settings UI fields**

In `_build_settings_tab`, move `settings_save` to row 1 and add:

```python
        self.widgets["watermark_content_label"] = ctk.CTkLabel(self.settings_tab)
        self.widgets["watermark_content_label"].grid(row=1, column=0, padx=(18, 8), pady=(8, 12), sticky="w")
        self.widgets["watermark_content"] = ctk.CTkEntry(self.settings_tab)
        self.widgets["watermark_content"].insert(0, self.settings.watermark_content)
        self.widgets["watermark_content"].grid(row=1, column=1, padx=8, pady=(8, 12), sticky="ew")
        self.widgets["watermark_password_label"] = ctk.CTkLabel(self.settings_tab)
        self.widgets["watermark_password_label"].grid(row=2, column=0, padx=(18, 8), pady=(8, 12), sticky="w")
        self.widgets["watermark_password"] = ctk.CTkEntry(self.settings_tab)
        self.widgets["watermark_password"].insert(0, self.settings.watermark_password)
        self.widgets["watermark_password"].grid(row=2, column=1, padx=8, pady=(8, 12), sticky="ew")
        self.widgets["settings_save"].grid(row=2, column=3, padx=(8, 18), pady=(8, 12))
        self.widgets["settings_status"].grid(row=3, column=0, columnspan=4, padx=18, pady=12, sticky="new")
```

- [ ] **Step 8: Add language labels**

In `_apply_language`, add:

```python
        self.widgets["pbr_add_watermark"].configure(text=text(self.language, "add_watermark"))
        self.widgets["watermark_length_label"].configure(text=text(self.language, "watermark_length"))
        self.widgets["watermark_files_button"].configure(text=text(self.language, "select_files"))
        self.widgets["watermark_clear_selected_button"].configure(text=text(self.language, "clear_selected"))
        self.widgets["watermark_add_button"].configure(text=text(self.language, "add_watermark"))
        self.widgets["watermark_detect_button"].configure(text=text(self.language, "detect_watermark"))
        self.widgets["watermark_content_label"].configure(text=text(self.language, "watermark_content"))
        self.widgets["watermark_password_label"].configure(text=text(self.language, "watermark_password"))
```

In `src/dayz_texture_tool/ui/i18n.py`, add these keys to both `zh` and `en` maps:

```python
        "watermark": "水印",
        "drop_watermark_files": "拖拽图片到这里",
        "drop_watermark_files_hint": "支持 PNG、JPG、BMP、TIF、TGA；PAA 需要先配置反解码工具",
        "add_watermark": "添加水印",
        "detect_watermark": "检测水印",
        "watermark_content": "水印内容",
        "watermark_password": "水印密码",
        "watermark_length": "水印长度",
        "watermark_done": "水印处理完成：成功 {ok}，失败 {fail}，跳过 {skip}。",
        "watermark_result": "检测结果：{value}",
```

For English:

```python
        "watermark": "Watermark",
        "drop_watermark_files": "Drop images here",
        "drop_watermark_files_hint": "Supports PNG, JPG, BMP, TIF, TGA; PAA requires a decode tool first",
        "add_watermark": "Add Watermark",
        "detect_watermark": "Detect Watermark",
        "watermark_content": "Watermark Content",
        "watermark_password": "Watermark Password",
        "watermark_length": "Watermark Length",
        "watermark_done": "Watermark done: {ok} succeeded, {fail} failed, {skip} skipped.",
        "watermark_result": "Detected: {value}",
```

- [ ] **Step 9: Add shared pending support for watermark page**

The existing `_pending_attr` already maps any page name using string formatting. Add methods:

```python
    def _watermark_pending_paths(self) -> list[Path]:
        return list(self.watermark_pending_paths)

    def _select_watermark_files(self) -> None:
        files = filedialog.askopenfilenames(filetypes=[("Images", "*.png *.tga *.tif *.tiff *.jpg *.jpeg *.bmp *.paa")])
        selected = self._unique_image_paths([Path(file) for file in files], SUPPORTED_WATERMARK_EXTENSIONS | {".paa"})
        if selected:
            self._set_pending_paths("watermark", selected)

    def _on_watermark_drop(self, event) -> None:
        paths = [Path(item) for item in self.tk.splitlist(event.data)]
        pending = []
        for path in paths:
            if path.is_dir():
                pending.extend(sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in SUPPORTED_WATERMARK_EXTENSIONS | {".paa"}))
            elif path.is_file() and path.suffix.lower() in SUPPORTED_WATERMARK_EXTENSIONS | {".paa"}:
                pending.append(path)
        if pending:
            self._set_pending_paths("watermark", self._unique_image_paths(pending, SUPPORTED_WATERMARK_EXTENSIONS | {".paa"}))
```

- [ ] **Step 10: Save watermark settings**

Add helper:

```python
    def _save_watermark_settings(self) -> None:
        if "watermark_content" in self.widgets:
            self.settings.watermark_content = self.widgets["watermark_content"].get()
        if "watermark_password" in self.widgets:
            self.settings.watermark_password = self.widgets["watermark_password"].get()
        if "watermark_length" in self.widgets:
            try:
                self.settings.watermark_length = int(self.widgets["watermark_length"].get() or "0")
            except ValueError:
                self.settings.watermark_length = 0
```

Call it from `_save_settings` and `_on_close` before `save_settings(self.settings)`.

- [ ] **Step 11: Pass PBR watermark options**

In `_start_pbr2dayz_selected`, read:

```python
        add_watermark = bool(self.widgets["pbr_add_watermark"].get())
        watermark_content = self.settings.watermark_content
        watermark_password = self.settings.watermark_password
```

Pass to `convert_pbr_files`:

```python
add_watermark=add_watermark,
watermark_content=watermark_content,
watermark_password=watermark_password,
```

- [ ] **Step 12: Add watermark page actions**

Add:

```python
    def _start_watermark_add_selected(self) -> None:
        selected_paths = self._selected_pending_paths("watermark")
        if not selected_paths:
            self.widgets["watermark_status"].configure(text=text(self.language, "no_input"))
            return
        self._save_watermark_settings()
        save_settings(self.settings)
        self._start_progress("watermark_progress")
        progress_callback = self._progress_callback("watermark_progress")
        self._run_async(lambda: add_watermark_files(selected_paths, self.settings.watermark_content, self.settings.watermark_password, progress_callback), "watermark_status", "watermark_progress")

    def _start_watermark_detect_selected(self) -> None:
        selected_paths = self._selected_pending_paths("watermark")
        if not selected_paths:
            self.widgets["watermark_status"].configure(text=text(self.language, "no_input"))
            return
        self._save_watermark_settings()
        save_settings(self.settings)
        self._start_progress("watermark_progress")
        progress_callback = self._progress_callback("watermark_progress")
        self._run_async(lambda: detect_watermark_files(selected_paths, self.settings.watermark_password, self.settings.watermark_length, progress_callback), "watermark_status", "watermark_progress")
```

- [ ] **Step 13: Update result display for watermark metadata**

In `_show_result`, after output count handling:

```python
        watermark_lengths = [item.metadata.get("watermark_length") for item in result.results if item.metadata.get("watermark_length")]
        watermark_texts = [item.metadata.get("watermark_text") for item in result.results if item.metadata.get("watermark_text")]
        if watermark_lengths:
            self.settings.watermark_length = int(watermark_lengths[-1])
            if "watermark_length" in self.widgets:
                self.widgets["watermark_length"].delete(0, "end")
                self.widgets["watermark_length"].insert(0, str(self.settings.watermark_length))
            save_settings(self.settings)
            message = f"{message} wm_bit={watermark_lengths[-1]}"
        if watermark_texts:
            message = f"{message} {text(self.language, 'watermark_result').format(value=watermark_texts[-1])}"
```

- [ ] **Step 14: Run focused UI test**

Run:

```powershell
rtk python -m unittest tests.test_ui_dragdrop.UIDragDropTests.test_pbr_process_selected_uses_selected_paths_only -v
```

Expected: PASS.

- [ ] **Step 15: Add UI test for watermark add action**

Append to `UIDragDropTests`:

```python
    def test_watermark_add_uses_selected_paths_and_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            one = root / "one.png"
            two = root / "two.png"
            one.write_bytes(b"png")
            two.write_bytes(b"png")
            app = DummyApp()
            app.watermark_pending_paths = []
            app.watermark_selected_paths = set()
            app.widgets["watermark_status"] = type("Widget", (), {"configure": lambda self, **kwargs: None})()

            main_window.DayZTextureToolApp._set_pending_paths(app, "watermark", [one, two])
            main_window.DayZTextureToolApp._select_pending_path(app, "watermark", two, False)

            with patch("dayz_texture_tool.ui.main_window.save_settings"), patch("dayz_texture_tool.ui.main_window.add_watermark_files") as process:
                main_window.DayZTextureToolApp._start_watermark_add_selected(app)
                app.work()

            process.assert_called_once()
            self.assertEqual(process.call_args.args[0], [one])
            self.assertEqual(process.call_args.args[1], "secret")
            self.assertEqual(process.call_args.args[2], "9")
```

- [ ] **Step 16: Run full UI tests**

Run:

```powershell
rtk python -m unittest tests.test_ui_dragdrop -v
```

Expected: PASS.

- [ ] **Step 17: Commit**

```powershell
rtk git add src/dayz_texture_tool/ui/main_window.py src/dayz_texture_tool/ui/i18n.py tests/test_ui_dragdrop.py
rtk git commit -m "feat: add watermark UI"
```

## Task 8: Final Verification

**Files:**
- All changed files
- CodeGraph index

- [ ] **Step 1: Run all tests**

Run:

```powershell
rtk python -m unittest discover tests -v
```

Expected: all tests PASS.

- [ ] **Step 2: Inspect git diff**

Run:

```powershell
rtk git diff --stat
```

Expected: changes are limited to dependency files, watermark processor, PBR2DayZ wiring, settings, UI/i18n, and tests.

- [ ] **Step 3: Sync CodeGraph index**

Run:

```powershell
rtk codegraph sync
```

Expected: CodeGraph reports changed files indexed or index up to date.

- [ ] **Step 4: Verify CodeGraph status**

Run:

```powershell
rtk codegraph status
```

Expected: `[OK] Index is up to date`.

- [ ] **Step 5: Final commit if Task 8 produced tracked changes**

If only `.codegraph` internals changed, do not commit them unless this repository already tracks those exact files. If test or code fixes were made, commit them:

```powershell
rtk git add <changed-source-or-test-files>
rtk git commit -m "test: verify watermark feature"
```

## Self-Review

- Spec coverage: PBR2DayZ adds a single switch, navigation gains Watermark page, Watermark page includes add and detect, Settings stores content/password/length, and PAA unsupported behavior is explicit.
- Placeholder scan: No unresolved placeholder markers or unspecified "add tests" steps remain. Each implementation step names files and concrete code.
- Type consistency: `watermark_content`, `watermark_password`, `watermark_length`, `add_watermark`, and `metadata` names are consistent across processor, settings, UI, and tests.
- Scope check: Direct PAA decoding is intentionally not implemented because no reverse PAA conversion tool exists in the current project. The user-facing behavior is a clear unsupported error for `.paa` standalone operations until a decode tool is introduced.
