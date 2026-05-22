from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from dayz_texture_tool.models import BatchResult, ProcessingResult


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tif", ".tiff"}

DEFAULT_PATTERNS = {
    "basecolor": ["basecolor", "base_color", "albedo", "diffuse", "_color", "_d", "_bm_rgb", "_rgb", "_sg_bm_rgb", "_mg_bm_rgb"],
    "normal": ["normal", "_n", "nrm", "nrml", "_mg_orn_n", "_sg_orn_n", "orn_n"],
    "roughness": ["roughness", "rough", "_r", "_mg_orn_rou", "_sg_orn_rou", "_orn_rou", "_rou"],
    "metallic": ["metallic", "metal", "_m", "_sg_bm_alpha", "_mg_bm_alpha", "_bm_alpha", "_alpha", "_b", "_mg_b", "_sg_b"],
    "ao": ["ao", "ambient", "occlusion", "_ao", "_occ", "_mg_orn_ao", "_sg_orn_ao", "_orn_ao"],
}


@dataclass
class PBRGroup:
    prefix: str
    directory: Path
    textures: dict[str, Path]


def _matches_keyword(stem: str, name_lower: str, keyword: str, match_mode: str) -> bool:
    kw = keyword.lower()
    if match_mode == "exact":
        return stem.endswith(kw)
    if kw.startswith("_"):
        return kw in stem
    if len(kw) <= 3:
        pattern = rf"(?<![a-z0-9]){re.escape(kw)}(?![a-z0-9])"
        return re.search(pattern, stem) is not None
    return kw in name_lower


def detect_texture_type(filename: str, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy") -> str | None:
    active_patterns = patterns or DEFAULT_PATTERNS
    name_lower = filename.lower()
    stem = Path(filename).stem.lower()
    for tex_type, keywords in active_patterns.items():
        for keyword in keywords:
            if _matches_keyword(stem, name_lower, keyword, match_mode):
                return tex_type
    return None


def _output_prefix(directory: Path, root: Path) -> str:
    if directory.name.lower() == "data" and directory.parent != directory:
        return directory.parent.name
    rel_dir = directory.relative_to(root)
    return root.name if str(rel_dir) == "." else directory.name


def scan_pbr_groups(folder: str | Path, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy") -> list[PBRGroup]:
    root = Path(folder)
    groups: dict[Path, PBRGroup] = {}
    for file_path in sorted(root.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        tex_type = detect_texture_type(file_path.name, patterns, match_mode)
        if tex_type is None:
            continue
        prefix = _output_prefix(file_path.parent, root)
        group = groups.setdefault(file_path.parent, PBRGroup(prefix=prefix, directory=file_path.parent, textures={}))
        if tex_type not in group.textures:
            group.textures[tex_type] = file_path
    return list(groups.values())


def _resolution(path: Path, requested: str) -> int:
    if requested != "auto":
        return int(requested)
    with Image.open(path) as image:
        return min(max(image.size), 2048)


def _save_tga(image: Image.Image, output: Path, resolution: int) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    image.resize((resolution, resolution), Image.Resampling.LANCZOS).save(output, format="TGA")
    return output


def convert_co_texture(base_color_path: Path, metal_path: Path | None, output_path: Path, co_mode: str, resolution: int) -> Path:
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


def convert_nohq_texture(normal_path: Path, output_path: Path, normal_type: str, resolution: int) -> Path:
    normal = Image.open(normal_path).convert("RGB")
    if normal_type == "directx":
        r_channel, g_channel, b_channel = normal.split()
        g_channel = Image.eval(g_channel, lambda x: 255 - x)
        normal = Image.merge("RGB", (r_channel, g_channel, b_channel))
    return _save_tga(normal, output_path, resolution)


def convert_smdi_texture(metal_path: Path | None, roughness_path: Path, output_path: Path, specular: float, glossiness: float, resolution: int) -> Path:
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


def convert_as_texture(ao_path: Path, output_path: Path, resolution: int) -> Path:
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
        completed = subprocess.run([str(image_to_paa), str(output)], capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            messages.append(f"ImageToPAA failed for {output.name}: {completed.stderr.strip() or completed.stdout.strip()}")


def _delete_sources(textures: dict[str, Path]) -> None:
    for source in set(textures.values()):
        if source.exists():
            source.unlink()


def convert_pbr_group(group: PBRGroup, normal_type: str = "directx", resolution: str = "auto", co_mode: str = "basecolor", specular: float = 0.75, glossiness: float = 1.0, make_paa: bool = False, image_to_paa: str | Path | None = None, delete_source: bool = False) -> ProcessingResult:
    start = time.time()
    outputs: list[Path] = []
    messages: list[str] = []
    try:
        textures = group.textures
        if "basecolor" in textures:
            res = _resolution(textures["basecolor"], resolution)
            outputs.append(convert_co_texture(textures["basecolor"], textures.get("metallic"), group.directory / f"{group.prefix}_co.tga", co_mode, res))
        if "normal" in textures:
            res = _resolution(textures["normal"], resolution)
            outputs.append(convert_nohq_texture(textures["normal"], group.directory / f"{group.prefix}_nohq.tga", normal_type, res))
        if "roughness" in textures:
            res = _resolution(textures["roughness"], resolution)
            outputs.append(convert_smdi_texture(textures.get("metallic"), textures["roughness"], group.directory / f"{group.prefix}_smdi.tga", specular, glossiness, res))
        if "ao" in textures:
            res = _resolution(textures["ao"], resolution)
            outputs.append(convert_as_texture(textures["ao"], group.directory / f"{group.prefix}_as.tga", res))
        if make_paa and outputs:
            paa_path = Path(image_to_paa) if image_to_paa else None
            _run_image_to_paa(outputs, paa_path, messages)
        if delete_source and outputs:
            _delete_sources(textures)
        elapsed = int((time.time() - start) * 1000)
        if not outputs:
            return ProcessingResult(False, processor="PBR2DayZ", elapsed_ms=elapsed, messages=[f"Skipped {group.prefix}: no convertible textures."])
        return ProcessingResult(True, outputs=outputs, processor="PBR2DayZ", elapsed_ms=elapsed, messages=messages)
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, processor="PBR2DayZ", elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}", messages=messages)


def convert_pbr_folder(folder: str | Path, normal_type: str = "directx", resolution: str = "auto", co_mode: str = "basecolor", specular: float = 0.75, glossiness: float = 1.0, make_paa: bool = False, image_to_paa: str | Path | None = None, patterns: dict[str, list[str]] | None = None, match_mode: str = "fuzzy", delete_source: bool = False) -> BatchResult:
    result = BatchResult()
    groups = scan_pbr_groups(folder, patterns, match_mode)
    result.messages.append(f"Scanned {folder}: found {len(groups)} PBR group(s).")
    for group in groups:
        result.add(convert_pbr_group(group, normal_type, resolution, co_mode, specular, glossiness, make_paa, image_to_paa, delete_source))
    if not groups:
        result.messages.append("No PBR textures found.")
    return result
