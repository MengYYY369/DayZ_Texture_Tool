from __future__ import annotations

import re
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.processors.watermark import add_watermark_in_place
from dayz_texture_tool.recycle import move_to_recycle_bin


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff"}

DEFAULT_PATTERNS = {
    "basecolor": ["basecolor", "base_color", "albedo", "diffuse", "_color", "_d", "_bm_rgb", "_rgb", "_sg_bm_rgb", "_mg_bm_rgb"],
    "normal": ["normal", "_n", "nrm", "nrml", "_mg_orn_n", "_sg_orn_n", "orn_n"],
    "roughness": ["roughness", "rough", "_r", "_mg_orn_rou", "_sg_orn_rou", "_orn_rou", "_rou"],
    "metallic": ["metallic", "metal", "_m", "_sg_bm_alpha", "_mg_bm_alpha", "_bm_alpha", "_alpha", "_b", "_mg_b", "_sg_b"],
    "ao": ["ao", "ambient", "occlusion", "_ao", "_occ", "_mg_orn_ao", "_sg_orn_ao", "_orn_ao"],
}

DEFAULT_OUTPUT_SUFFIXES = {
    "co": "_co",
    "nohq": "_nohq",
    "smdi": "_smdi",
    "as": "_as",
}


@dataclass
class PBRGroup:
    prefix: str
    directory: Path
    textures: dict[str, Path]


def _matches_keyword(stem: str, name_lower: str, keyword: str, match_mode: str) -> bool:
    kw = keyword.lower()
    if match_mode == "exact":
        if kw.startswith(("_", "-", ".", " ")):
            return stem.endswith(kw)
        pattern = rf"(?<![a-z0-9]){re.escape(kw)}$"
        return re.search(pattern, stem) is not None
    if kw.startswith("_"):
        return kw in stem
    if len(kw) <= 3:
        pattern = rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])"
        return re.search(pattern, stem) is not None
    return kw in name_lower


def detect_texture_type(filename: str, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy") -> str | None:
    match = detect_texture_match(filename, patterns, match_mode)
    return match[0] if match else None


def detect_texture_match(filename: str, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy") -> tuple[str, str] | None:
    active_patterns = patterns or DEFAULT_PATTERNS
    name_lower = filename.lower()
    stem = Path(filename).stem.lower()
    for tex_type, keywords in active_patterns.items():
        for keyword in keywords:
            if _matches_keyword(stem, name_lower, keyword, match_mode):
                return tex_type, keyword
    return None


def _is_data_folder(directory: Path) -> bool:
    """DayZ 插件的 data 目录：产物按插件名命名，不按文件名。"""
    return directory.name.lower() == "data" and directory.parent != directory


def _output_prefix(directory: Path, root: Path, prefix_mode: str = "auto", custom_prefix: str = "") -> str:
    if prefix_mode == "custom" and custom_prefix.strip():
        return custom_prefix.strip()
    if prefix_mode == "current_folder":
        return directory.name
    if prefix_mode == "parent_folder" and directory.parent != directory:
        return directory.parent.name
    if _is_data_folder(directory):
        return directory.parent.name
    try:
        rel_dir = directory.relative_to(root)
    except ValueError:
        # 跨盘符的文件没有共同根目录，退回文件夹名
        return directory.name
    return root.name if str(rel_dir) == "." else directory.name


def _filename_prefix(filename: str, keyword: str, match_mode: str) -> str:
    stem = Path(filename).stem
    stem_lower = stem.lower()
    kw = keyword.lower()
    if match_mode == "exact":
        if kw.startswith(("_", "-", ".", " ")) and stem_lower.endswith(kw):
            return stem[:-len(kw)].rstrip("_-. ")
        match = re.search(rf"(?<![a-z0-9]){re.escape(kw)}$", stem_lower)
        if match:
            return stem[:match.start()].rstrip("_-. ")
        return stem
    index = stem_lower.rfind(kw)
    if index > 0:
        return stem[:index].rstrip("_-. ")
    return stem


def _filename_prefix_for(name: str, keyword: str, match_mode: str) -> str:
    """文件名里关键词前面那串字。整名就是关键词（也就是取不出前缀）时给空串。"""
    prefix = _filename_prefix(name, keyword, match_mode)
    if prefix and len(prefix) < len(Path(name).stem):
        return prefix
    return ""


def _shared_prefixes(directory: Path, entries: list[tuple[Path, str, str]], prefix_mode: str, match_mode: str) -> dict[Path, str]:
    """一个文件夹里的文件各算哪个前缀。空字典 = 整批按文件夹名走。"""
    if prefix_mode not in ("auto", "filename_prefix"):
        return {}
    if prefix_mode == "auto" and _is_data_folder(directory):
        # data 文件夹按插件名（上层文件夹名）走老规矩
        return {}
    # 每个文件去掉命中的关键词，剩下的那串字就是它的前缀
    guesses = {
        file_path: _filename_prefix_for(file_path.name, keyword, match_mode)
        for file_path, _, keyword in entries
    }
    # 一套图里每种贴图的关键词写法常常不一样（_C / _MRA_met / _NCE_normal），
    # 去完会剩下 _ni / _ni_MRA / _ni_NCE 这种长短不一的名字。
    # 谁是谁的开头就算同一套，取最短的那个当名字。
    names: list[str] = []
    for guess in sorted({value for value in guesses.values() if value}, key=len):
        if not any(guess.startswith(name) for name in names):
            names.append(guess)
    return {
        file_path: next(name for name in names if guess.startswith(name))
        for file_path, guess in guesses.items()
        if guess
    }


def _is_own_output(path: Path) -> bool:
    """本工具自己写出来的产物（xxx_co.tga 这种），再扫一遍时不能当成原图。

    只有 .tga 要管：产物都是 .tga，而 xxx_nohq.tga 里的 _n 会被模糊匹配
    认成法线图，把真正的新法线原图顶掉。
    """
    if path.suffix.lower() != ".tga":
        return False
    stem = path.stem.lower()
    return any(stem.endswith(suffix) for suffix in DEFAULT_OUTPUT_SUFFIXES.values())


def scan_pbr_paths(paths: list[Path], root: Path, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy", prefix_mode: str = "auto", custom_prefix: str = "") -> list[PBRGroup]:
    # 先按文件夹归拢：auto 模式要看完一个文件夹里的所有文件，才知道能不能按文件名分组
    found: dict[Path, list[tuple[Path, str, str]]] = {}
    for file_path in sorted(paths):
        if not file_path.is_file() or file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        if _is_own_output(file_path):
            continue
        match = detect_texture_match(file_path.name, patterns, match_mode)
        if match is None:
            continue
        found.setdefault(file_path.parent, []).append((file_path, match[0], match[1]))

    groups: dict[tuple[Path, str], PBRGroup] = {}
    for directory, entries in found.items():
        folder_prefix = _output_prefix(directory, root, prefix_mode, custom_prefix)
        prefixes = _shared_prefixes(directory, entries, prefix_mode, match_mode)
        for file_path, tex_type, _ in entries:
            prefix = prefixes.get(file_path, folder_prefix)
            group_key = (directory, prefix)
            group = groups.setdefault(
                group_key, PBRGroup(prefix=prefix, directory=directory, textures={})
            )
            if tex_type not in group.textures:
                group.textures[tex_type] = file_path
    return list(groups.values())


def scan_pbr_groups(folder: str | Path, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy", prefix_mode: str = "auto", custom_prefix: str = "") -> list[PBRGroup]:
    root = Path(folder)
    return scan_pbr_paths(list(root.rglob("*")), root, patterns, match_mode, prefix_mode, custom_prefix)


def root_context_for_files(files: list[Path], root_context: str | Path | None = None) -> Path:
    if root_context is not None:
        root = Path(root_context)
    elif files:
        try:
            root = Path(os.path.commonpath([str(path.parent) for path in files]))
        except ValueError:
            # 跨盘符（D:\ 和 C:\）没有共同路径，退回第一张图所在的文件夹
            root = Path(files[0]).parent
    else:
        root = Path(".")
    if root.name.lower() == "data" and root.parent != root:
        return root.parent
    return root


def _resolution(path: Path, requested: str) -> tuple[int, int]:
    if requested != "auto":
        size = int(requested)
        return size, size
    with Image.open(path) as image:
        width, height = image.size
        max_side = max(width, height)
        if max_side <= 2048:
            return width, height
        scale = 2048 / max_side
        return max(1, round(width * scale)), max(1, round(height * scale))


def _save_tga(image: Image.Image, output: Path, resolution: tuple[int, int]) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    image.resize(resolution, Image.Resampling.LANCZOS).save(output, format="TGA")
    return output


def _output_suffixes(output_suffixes: dict[str, str] | None = None) -> dict[str, str]:
    suffixes = dict(DEFAULT_OUTPUT_SUFFIXES)
    if output_suffixes:
        for key, suffix in output_suffixes.items():
            if key in suffixes:
                suffixes[key] = str(suffix)
    return suffixes


def _group_output_path(group: PBRGroup, suffixes: dict[str, str], key: str) -> Path:
    """一组 PBR 贴图的产物路径。convert_pbr_group 和 plan_group_outputs 共用这一条规则。"""
    return group.directory / f"{group.prefix}{suffixes[key]}.tga"


def plan_group_outputs(group: PBRGroup, output_suffixes: dict[str, str] | None = None) -> list[Path]:
    """这一组会产出哪些 .tga，不真的处理。顺序跟 convert_pbr_group 一致。

    只算确定的那一步（四张 .tga）；make_paa / delete_source 是后置步骤，可能把 .tga
    换成 .paa，实际产物以处理结果为准。"""
    suffixes = _output_suffixes(output_suffixes)
    outputs: list[Path] = []
    for tex_type, key in (("basecolor", "co"), ("normal", "nohq"), ("roughness", "smdi"), ("ao", "as")):
        if tex_type in group.textures:
            outputs.append(_group_output_path(group, suffixes, key))
    return outputs


def convert_co_texture(base_color_path: Path, metal_path: Path | None, output_path: Path, co_mode: str, resolution: tuple[int, int]) -> Path:
    base_color = Image.open(base_color_path).convert("RGB")
    if co_mode != "specular":
        return _save_tga(base_color, output_path, resolution)
    if metal_path is None:
        metal_map = Image.new("L", base_color.size, 0)
    else:
        metal_map = Image.open(metal_path).convert("L")
    base_np = np.array(base_color, dtype=np.float32) / 255.0
    metal_np = np.array(metal_map, dtype=np.float32) / 255.0
    specular_color = base_np * metal_np[..., None] + (1.0 - metal_np[..., None]) * 0.04
    specular_factor = np.max(specular_color, axis=2, keepdims=True)
    diffuse_color = base_np * (1.0 - specular_factor)
    image = Image.fromarray(np.clip(diffuse_color * 255, 0, 255).astype(np.uint8), "RGB")
    return _save_tga(image, output_path, resolution)


def convert_nohq_texture(normal_path: Path, output_path: Path, normal_type: str, resolution: tuple[int, int]) -> Path:
    normal = Image.open(normal_path).convert("RGB")
    if normal_type == "directx":
        r_channel, g_channel, b_channel = normal.split()
        g_channel = Image.eval(g_channel, lambda x: 255 - x)
        normal = Image.merge("RGB", (r_channel, g_channel, b_channel))
    return _save_tga(normal, output_path, resolution)


def convert_smdi_texture(metal_path: Path | None, roughness_path: Path, output_path: Path, specular: float, glossiness: float, resolution: tuple[int, int]) -> Path:
    roughness = Image.open(roughness_path).convert("L")
    if metal_path is None:
        metallic = Image.new("L", roughness.size, 0)
    else:
        metallic = Image.open(metal_path).convert("L")
    metal_np = np.array(metallic, dtype=np.float32) / 255.0
    rough_np = np.array(roughness, dtype=np.float32) / 255.0
    specular_channel = np.clip((metal_np + (1.0 - metal_np) * 0.04) * specular * 255.0, 0, 255).astype(np.uint8)
    gloss_channel = np.clip((1.0 - rough_np) * glossiness * 255.0, 0, 255).astype(np.uint8)
    red_channel = np.full(specular_channel.shape, 255, dtype=np.uint8)
    smdi = Image.fromarray(np.dstack([red_channel, specular_channel, gloss_channel]), "RGB")
    return _save_tga(smdi, output_path, resolution)


def convert_as_texture(ao_path: Path, output_path: Path, resolution: tuple[int, int]) -> Path:
    ao = Image.open(ao_path).convert("L")
    inverted_ao = Image.eval(ao, lambda x: 255 - x)
    black = Image.new("L", ao.size, 0)
    as_texture = Image.merge("RGB", (black, inverted_ao, black))
    final_as = Image.eval(as_texture, lambda x: 255 - x)
    return _save_tga(final_as, output_path, resolution)


def _run_image_to_paa(outputs: list[Path], image_to_paa: Path | None, messages: list[str]) -> None:
    if image_to_paa is None or not image_to_paa.exists():
        messages.append("ImageToPAA.exe path is missing or invalid; PAA conversion skipped.")
        return
    for output in outputs:
        run_kwargs = {"capture_output": True, "text": True, "check": False}
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        completed = subprocess.run([str(image_to_paa), str(output)], **run_kwargs)
        if completed.returncode != 0:
            messages.append(f"ImageToPAA failed for {output.name}: {completed.stderr.strip() or completed.stdout.strip()}")


def _delete_sources(textures: dict[str, Path]) -> None:
    for source in set(textures.values()):
        if source.exists():
            move_to_recycle_bin(source)


def _delete_tga_outputs_with_paa(outputs: list[Path]) -> list[Path]:
    final_outputs = []
    for output in outputs:
        paa_output = output.with_suffix(".paa")
        if paa_output.exists():
            if output.exists():
                output.unlink()
            final_outputs.append(paa_output)
        else:
            final_outputs.append(output)
    return final_outputs


def _add_watermarks(outputs: list[Path], content: str, password: str | int, messages: list[str], image_to_paa: str | Path | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {}
    for output in outputs:
        result = add_watermark_in_place(output, content, password, image_to_paa=image_to_paa)
        messages.extend(result.messages)
        if not result.success:
            raise RuntimeError(result.error)
        if "watermark_length" in result.metadata:
            metadata["watermark_length"] = result.metadata["watermark_length"]
    return metadata


def convert_pbr_group(group: PBRGroup, normal_type: str = "directx", resolution: str = "auto", co_mode: str = "basecolor", specular: float = 0.75, glossiness: float = 1.0, make_paa: bool = False, image_to_paa: str | Path | None = None, delete_source: bool = False, output_suffixes: dict[str, str] | None = None, add_watermark: bool = False, watermark_content: str = "", watermark_password: str | int = 1) -> ProcessingResult:
    start = time.time()
    outputs: list[Path] = []
    messages: list[str] = []
    metadata: dict[str, object] = {}
    try:
        textures = group.textures
        suffixes = _output_suffixes(output_suffixes)
        if "basecolor" in textures:
            res = _resolution(textures["basecolor"], resolution)
            outputs.append(convert_co_texture(textures["basecolor"], textures.get("metallic"), _group_output_path(group, suffixes, "co"), co_mode, res))
        if "normal" in textures:
            res = _resolution(textures["normal"], resolution)
            outputs.append(convert_nohq_texture(textures["normal"], _group_output_path(group, suffixes, "nohq"), normal_type, res))
        if "roughness" in textures:
            res = _resolution(textures["roughness"], resolution)
            outputs.append(convert_smdi_texture(textures.get("metallic"), textures["roughness"], _group_output_path(group, suffixes, "smdi"), specular, glossiness, res))
        if "ao" in textures:
            res = _resolution(textures["ao"], resolution)
            outputs.append(convert_as_texture(textures["ao"], _group_output_path(group, suffixes, "as"), res))
        if add_watermark and outputs:
            metadata.update(_add_watermarks(outputs, watermark_content, watermark_password, messages, image_to_paa))
        if make_paa and outputs:
            paa_path = Path(image_to_paa) if image_to_paa else None
            _run_image_to_paa(outputs, paa_path, messages)
            if delete_source:
                outputs = _delete_tga_outputs_with_paa(outputs)
        if delete_source and outputs:
            _delete_sources(textures)
        elapsed = int((time.time() - start) * 1000)
        if not outputs:
            return ProcessingResult(False, processor="PBR2DayZ", elapsed_ms=elapsed, messages=[f"Skipped {group.prefix}: no convertible textures."])
        return ProcessingResult(True, outputs=outputs, processor="PBR2DayZ", elapsed_ms=elapsed, messages=messages, metadata=metadata)
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, processor="PBR2DayZ", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}", messages=messages, metadata=metadata)


ProgressCallback = Callable[[int, int, str], None]


def convert_pbr_folder(folder: str | Path, normal_type: str = "directx", resolution: str = "auto", co_mode: str = "basecolor", specular: float = 0.75, glossiness: float = 1.0, make_paa: bool = False, image_to_paa: str | Path | None = None, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy", delete_source: bool = False, output_suffixes: dict[str, str] | None = None, prefix_mode: str = "auto", custom_prefix: str = "", progress_callback: ProgressCallback | None = None, add_watermark: bool = False, watermark_content: str = "", watermark_password: str | int = 1) -> BatchResult:
    result = BatchResult()
    groups = scan_pbr_groups(folder, patterns, match_mode, prefix_mode, custom_prefix)
    result.messages.append(f"Scanned {folder}: found {len(groups)} PBR group(s).")
    total = len(groups)
    for index, group in enumerate(groups, start=1):
        result.add(convert_pbr_group(group, normal_type, resolution, co_mode, specular, glossiness, make_paa, image_to_paa, delete_source, output_suffixes, add_watermark, watermark_content, watermark_password))
        if progress_callback:
            progress_callback(index, total, group.prefix)
    if not groups:
        result.messages.append("No PBR textures found.")
    return result


def convert_pbr_files(files: list[str | Path], root_context: str | Path | None = None, normal_type: str = "directx", resolution: str = "auto", co_mode: str = "basecolor", specular: float = 0.75, glossiness: float = 1.0, make_paa: bool = False, image_to_paa: str | Path | None = None, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy", delete_source: bool = False, output_suffixes: dict[str, str] | None = None, prefix_mode: str = "auto", custom_prefix: str = "", progress_callback: ProgressCallback | None = None, add_watermark: bool = False, watermark_content: str = "", watermark_password: str | int = 1) -> BatchResult:
    result = BatchResult()
    file_paths = [Path(file) for file in files]
    root = root_context_for_files(file_paths, root_context)
    groups = scan_pbr_paths(file_paths, root, patterns, match_mode, prefix_mode, custom_prefix)
    result.messages.append(f"Selected {len(file_paths)} PBR file(s): found {len(groups)} PBR group(s).")
    total = len(groups)
    for index, group in enumerate(groups, start=1):
        result.add(convert_pbr_group(group, normal_type, resolution, co_mode, specular, glossiness, make_paa, image_to_paa, delete_source, output_suffixes, add_watermark, watermark_content, watermark_password))
        if progress_callback:
            progress_callback(index, total, group.prefix)
    if not groups:
        result.messages.append("No PBR textures found.")
    return result
