from __future__ import annotations

import time
import tempfile
import hashlib
from pathlib import Path
from typing import Callable

from PIL import Image

from dayz_texture_tool.models import BatchResult, ProcessingResult


try:
    from blind_watermark import WaterMark
except ImportError:
    WaterMark = None


SUPPORTED_WATERMARK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".tga"}

ProgressCallback = Callable[[int, int, str], None]


def _password(value: str | int) -> int:
    text = str(value).strip()
    if not text:
        return 1
    try:
        return int(text)
    except ValueError:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "big") or 1


def _output_path(path: Path, output_path: str | Path | None = None) -> Path:
    if output_path is not None:
        return Path(output_path)
    return path.with_name(f"{path.stem}_watermarked{path.suffix}")


def _unsupported_paa(path: Path) -> ProcessingResult | None:
    if path.suffix.lower() == ".paa":
        return ProcessingResult(False, input_path=path, processor="Watermark", error="PAA watermarking requires a PAA decode tool before blind_watermark can process it.")
    return None


def _unsupported_image(path: Path) -> ProcessingResult | None:
    if path.suffix.lower() not in SUPPORTED_WATERMARK_EXTENSIONS:
        return ProcessingResult(False, input_path=path, processor="Watermark", error=f"Unsupported image extension for watermark: {path.suffix}")
    return None


def _watermark_class():
    if WaterMark is None:
        raise RuntimeError("blind-watermark is not installed. Install requirements.txt first.")
    return WaterMark


def _is_tga(path: Path) -> bool:
    return path.suffix.lower() == ".tga"


def _save_as_png(source: Path, output: Path) -> None:
    with Image.open(source) as image:
        image.save(output, "PNG")


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
        bwm = _watermark_class()(password_img=pwd, password_wm=pwd)
        if _is_tga(path):
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                readable_input = tmp_root / "input.png"
                readable_output = tmp_root / "output.png"
                _save_as_png(path, readable_input)
                bwm.read_img(str(readable_input))
                bwm.read_wm(content, mode="str")
                bwm.embed(str(readable_output))
                with Image.open(readable_output) as image:
                    image.save(output, "TGA")
        else:
            bwm.read_img(str(path))
            bwm.read_wm(content, mode="str")
            bwm.embed(str(output))
        length = len(bwm.wm_bit)
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(True, input_path=path, outputs=[output], processor="Watermark", elapsed_ms=elapsed, messages=[f"Watermark embedded in {output.name}; wm_bit length: {length}."], metadata={"watermark_length": length})
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
        bwm = _watermark_class()(password_img=pwd, password_wm=pwd)
        if _is_tga(path):
            with tempfile.TemporaryDirectory() as tmp:
                readable_input = Path(tmp) / "input.png"
                _save_as_png(path, readable_input)
                extracted = bwm.extract(str(readable_input), wm_shape=watermark_length, mode="str")
        else:
            extracted = bwm.extract(str(path), wm_shape=watermark_length, mode="str")
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(True, input_path=path, processor="Watermark", elapsed_ms=elapsed, messages=[f"Extracted watermark from {path.name}: {extracted}"], metadata={"watermark_text": extracted})
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
