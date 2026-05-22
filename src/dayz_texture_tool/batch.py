from __future__ import annotations

from pathlib import Path

from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.processors.game2pbr import SUPPORTED_EXTENSIONS, process_game2pbr


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


def process_game2pbr_auto(path: str | Path, suffix_map: dict[str, list[str]] | None = None, match_mode: str = "exact", delete_source: bool = False) -> BatchResult:
    result = BatchResult()
    files = collect_image_files(path)
    result.messages.append(f"Scanned {path}: found {len(files)} image file(s).")
    for file_path in files:
        processor = detect_game2pbr_processor(file_path, suffix_map, match_mode)
        if processor is None:
            skipped = ProcessingResult(False, input_path=file_path, messages=[f"Skipped {file_path.name}: no matching suffix."])
            result.add(skipped)
            continue
        item_result = process_game2pbr(file_path, processor, delete_source=delete_source)
        item_result.messages.append(f"{processor}: {file_path.name}")
        result.add(item_result)
    return result


def process_game2pbr_files(files: list[str | Path], processor: str, delete_source: bool = False) -> BatchResult:
    result = BatchResult()
    result.messages.append(f"Processing {len(files)} selected file(s) with {processor}.")
    for file_path in files:
        item_result = process_game2pbr(file_path, processor, delete_source=delete_source)
        item_result.messages.append(f"{processor}: {Path(file_path).name}")
        result.add(item_result)
    return result
