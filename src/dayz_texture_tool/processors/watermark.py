from __future__ import annotations

import time
import tempfile
import hashlib
import subprocess
import shutil
from pathlib import Path
from typing import Callable

from PIL import Image

from dayz_texture_tool.models import BatchResult, ProcessingResult


try:
    from blind_watermark import WaterMark
except ImportError:
    WaterMark = None


SUPPORTED_WATERMARK_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".tga", ".paa"}

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


def _is_paa(path: Path) -> bool:
    return path.suffix.lower() == ".paa"


def _save_as_png(source: Path, output: Path) -> None:
    with Image.open(source) as image:
        image.save(output, "PNG")


def _run_external_tool(tool_path: Path, source: Path, output: Path) -> None:
    if not tool_path.exists():
        raise FileNotFoundError(f"ImageToPAA.exe path is missing or invalid: {tool_path}")
    run_kwargs = {"capture_output": True, "text": True, "check": False}
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    completed = subprocess.run([str(tool_path), str(source), str(output)], **run_kwargs)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(detail or f"{tool_path.name} failed with exit code {completed.returncode}.")


def _embed_to_png(source: Path, output: Path, content: str, password: str | int) -> int:
    pwd = _password(password)
    bwm = _watermark_class()(password_img=pwd, password_wm=pwd)
    bwm.read_img(str(source))
    bwm.read_wm(content, mode="str")
    bwm.embed(str(output))
    return len(bwm.wm_bit)


def add_watermark(input_path: str | Path, content: str, password: str | int = 1, output_path: str | Path | None = None, image_to_paa: str | Path | None = None, overwrite: bool = False) -> ProcessingResult:
    start = time.time()
    path = Path(input_path)
    if not content:
        return ProcessingResult(False, input_path=path, processor="Watermark", error="Watermark content is empty.")
    unsupported = _unsupported_image(path)
    if unsupported is not None:
        return unsupported
    try:
        output = path if overwrite else _output_path(path, output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        if _is_paa(path):
            if image_to_paa is None:
                raise FileNotFoundError("ImageToPAA.exe path is missing or invalid.")
            tool_path = Path(image_to_paa)
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                readable_input = tmp_root / "input.png"
                readable_output = tmp_root / "output.png"
                temporary_paa = tmp_root / output.name
                _run_external_tool(tool_path, path, readable_input)
                length = _embed_to_png(readable_input, readable_output, content, password)
                _run_external_tool(tool_path, readable_output, temporary_paa)
                shutil.move(str(temporary_paa), str(output))
        elif _is_tga(path):
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                readable_input = tmp_root / "input.png"
                readable_output = tmp_root / "output.png"
                _save_as_png(path, readable_input)
                length = _embed_to_png(readable_input, readable_output, content, password)
                with Image.open(readable_output) as image:
                    image.save(output, "TGA")
        else:
            length = _embed_to_png(path, output, content, password)
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(True, input_path=path, outputs=[output], processor="Watermark", elapsed_ms=elapsed, messages=[f"Watermark embedded in {output.name}; wm_bit length: {length}."], metadata={"watermark_length": length})
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, input_path=path, processor="Watermark", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}")


def add_watermark_in_place(input_path: str | Path, content: str, password: str | int = 1, image_to_paa: str | Path | None = None) -> ProcessingResult:
    path = Path(input_path)
    temp_output = path.with_name(f"{path.stem}.__watermark_tmp__{path.suffix}")
    result = add_watermark(path, content, password, temp_output, image_to_paa=image_to_paa)
    if not result.success:
        return result
    temp_output.replace(path)
    result.outputs = [path]
    result.messages = [f"Watermark embedded in {path.name}; wm_bit length: {result.metadata['watermark_length']}."]
    return result


def detect_watermark(input_path: str | Path, password: str | int = 1, watermark_length: int = 0, image_to_paa: str | Path | None = None) -> ProcessingResult:
    start = time.time()
    path = Path(input_path)
    if watermark_length <= 0:
        return ProcessingResult(False, input_path=path, processor="Watermark", error="Watermark length must be greater than 0.")
    unsupported = _unsupported_image(path)
    if unsupported is not None:
        return unsupported
    try:
        pwd = _password(password)
        bwm = _watermark_class()(password_img=pwd, password_wm=pwd)
        if _is_paa(path):
            if image_to_paa is None:
                raise FileNotFoundError("ImageToPAA.exe path is missing or invalid.")
            with tempfile.TemporaryDirectory() as tmp:
                readable_input = Path(tmp) / "input.png"
                _run_external_tool(Path(image_to_paa), path, readable_input)
                extracted = bwm.extract(str(readable_input), wm_shape=watermark_length, mode="str")
        elif _is_tga(path):
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


def add_watermark_files(files: list[str | Path], content: str, password: str | int = 1, progress_callback: ProgressCallback | None = None, image_to_paa: str | Path | None = None, overwrite: bool = False) -> BatchResult:
    result = BatchResult()
    total = len(files)
    for index, file_path in enumerate(files, start=1):
        item = add_watermark(file_path, content, password, image_to_paa=image_to_paa, overwrite=overwrite)
        result.add(item)
        if progress_callback:
            progress_callback(index, total, Path(file_path).name)
    return result


def detect_watermark_files(files: list[str | Path], password: str | int = 1, watermark_length: int = 0, progress_callback: ProgressCallback | None = None, image_to_paa: str | Path | None = None) -> BatchResult:
    result = BatchResult()
    total = len(files)
    for index, file_path in enumerate(files, start=1):
        item = detect_watermark(file_path, password, watermark_length, image_to_paa=image_to_paa)
        result.add(item)
        if progress_callback:
            progress_callback(index, total, Path(file_path).name)
    return result
