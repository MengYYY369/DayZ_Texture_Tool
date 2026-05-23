from __future__ import annotations

from pathlib import Path
from typing import Callable

from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.processors.game2pbr import DEFAULT_OUTPUT_SUFFIXES, SUPPORTED_EXTENSIONS, process_game2pbr


DEFAULT_AUTO_SUFFIXES = {
    "DF_NRM": ["_nrm"],
    "DF_MRA": ["_mra"],
    "ABI_ORN": ["_orn"],
}


def collect_image_files(path: str | Path) -> list[Path]:
    root = Path(path)
    if root.is_file():
        return [root] if root.suffix.lower() in SUPPORTED_EXTENSIONS else []
    return sorted(file_path for file_path in root.rglob("*") if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS)


def _normalized_suffix_map(suffix_map: dict[str, list[str]] | None = None) -> dict[str, list[str]]:
    active = suffix_map or DEFAULT_AUTO_SUFFIXES
    normalized = {}
    for processor, suffixes in active.items():
        normalized[processor] = [suffix.strip().lower() for suffix in suffixes if suffix.strip()]
    return normalized


def _matches(stem: str, suffix: str, match_mode: str) -> bool:
    if match_mode == "fuzzy":
        return suffix in stem
    return stem.endswith(suffix)


def detect_game2pbr_processor(path: Path, suffix_map: dict[str, list[str]] | None = None, match_mode: str = "exact") -> str | None:
    stem = path.stem.lower()
    for processor, suffixes in _normalized_suffix_map(suffix_map).items():
        for suffix in suffixes:
            if _matches(stem, suffix, match_mode):
                return processor
    return None


def _output_suffixes_for(processor: str, output_suffix_map: dict[str, dict[str, str]] | None = None) -> dict[str, str]:
    suffixes = dict(DEFAULT_OUTPUT_SUFFIXES.get(processor, {}))
    if output_suffix_map and processor in output_suffix_map:
        suffixes.update({key: str(value) for key, value in output_suffix_map[processor].items()})
    return suffixes


def _is_generated_output(path: Path, processor: str, output_suffix_map: dict[str, dict[str, str]] | None = None) -> bool:
    stem = path.stem.lower()
    for suffix in _output_suffixes_for(processor, output_suffix_map).values():
        if suffix and stem.endswith(suffix.lower()):
            return True
    return False


ProgressCallback = Callable[[int, int, str], None]


def process_game2pbr_auto(path: str | Path, suffix_map: dict[str, list[str]] | None = None, match_mode: str = "exact", delete_source: bool = False, output_suffix_map: dict[str, dict[str, str]] | None = None, progress_callback: ProgressCallback | None = None) -> BatchResult:
    result = BatchResult()
    files = collect_image_files(path)
    result.messages.append(f"Scanned {path}: found {len(files)} image file(s).")
    total = len(files)
    for index, file_path in enumerate(files, start=1):
        processor = detect_game2pbr_processor(file_path, suffix_map, match_mode)
        if processor is None:
            skipped = ProcessingResult(False, input_path=file_path, messages=[f"Skipped {file_path.name}: no matching suffix."])
            result.add(skipped)
            if progress_callback:
                progress_callback(index, total, file_path.name)
            continue
        if _is_generated_output(file_path, processor, output_suffix_map):
            skipped = ProcessingResult(False, input_path=file_path, messages=[f"Skipped {file_path.name}: generated output suffix."])
            result.add(skipped)
            if progress_callback:
                progress_callback(index, total, file_path.name)
            continue
        suffixes = output_suffix_map.get(processor, {}) if output_suffix_map else None
        item_result = process_game2pbr(file_path, processor, delete_source=delete_source, output_suffixes=suffixes)
        item_result.messages.append(f"{processor}: {file_path.name}")
        result.add(item_result)
        if progress_callback:
            progress_callback(index, total, file_path.name)
    return result


def process_game2pbr_files(files: list[str | Path], processor: str, delete_source: bool = False, output_suffixes: dict[str, str] | None = None, progress_callback: ProgressCallback | None = None) -> BatchResult:
    result = BatchResult()
    result.messages.append(f"Processing {len(files)} selected file(s) with {processor}.")
    total = len(files)
    for index, file_path in enumerate(files, start=1):
        item_result = process_game2pbr(file_path, processor, delete_source=delete_source, output_suffixes=output_suffixes)
        item_result.messages.append(f"{processor}: {Path(file_path).name}")
        result.add(item_result)
        if progress_callback:
            progress_callback(index, total, Path(file_path).name)
    return result
