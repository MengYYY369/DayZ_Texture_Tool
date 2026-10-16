from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

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
    run_kwargs: dict[str, Any] = {"capture_output": True, "text": True, "check": False}
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
    try:
        if path.suffix.lower() not in SUPPORTED_SMDI_EXTENSIONS:
            return ProcessingResult(False, input_path=path, processor="SMDI", elapsed_ms=int((time.time() - start) * 1000), error=f"Unsupported image extension for SMDI: {path.suffix}")
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


def plan_outputs(path: Path, make_paa: bool) -> list[Path]:
    """这一张图最终会留下哪个文件，不真的处理。make_paa 时中间那张 .tga 会被删掉，
    所以只算 .paa —— 规划结果跟实际产物一致（dry-run 就靠它）。"""
    return [smdi_output_path(path, make_paa)]


def _planned_outputs(path: Path, make_paa: bool) -> list[Path]:
    """冲突预检用：除了最终产物，make_paa 时那张会被清理掉的 .tga 也算上 —— 它要是
    跟别人的输入撞名，同样会被这个批次毁掉。"""
    outputs = list(plan_outputs(path, make_paa))
    if make_paa:
        outputs.append(smdi_output_path(path, False))
    return outputs


def _batch_conflict(path: Path, inputs: set[str], claimed: dict[str, Path], make_paa: bool) -> str:
    outputs = _planned_outputs(path, make_paa)
    keys = [_path_key(output) for output in outputs]
    for output, key in zip(outputs, keys, strict=True):
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
