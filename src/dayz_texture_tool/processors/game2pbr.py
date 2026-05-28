from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image

from dayz_texture_tool.models import ProcessingResult
from dayz_texture_tool.recycle import move_to_recycle_bin


SUPPORTED_EXTENSIONS = {".png", ".tga", ".tif", ".tiff", ".jpg", ".jpeg", ".bmp", ".dds"}

DEFAULT_OUTPUT_SUFFIXES = {
    "SplitColorAlphaProcessor": {"rgb": "_rgb", "alpha": "_alpha"},
    "SplitRGBAProcessor": {"r": "_r", "g": "_g", "b": "_b", "a": "_a"},
    "MergeRGBAProcessor": {"merged": "_merged"},
    "XYNormalMapProcessor": {"normal": "_normal"},
    "DirectConvertProcessor": {"converted": ""},
    "DirectinvertProcessor": {"inverted": "_invert"},
    "DF_NRM": {"metal": "_Metal", "roughness": "_Rou", "normal": "_N"},
    "DF_MRA": {"metal": "_met", "roughness": "_rou", "ao": "_ao"},
    "ABI_ORN": {"roughness": "_Rou", "ao": "_AO", "normal": "_N"},
}


def _load_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGBA"), dtype=np.uint8)


def _save_rgba(arr: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGBA").save(path)
    return path


def _gray(channel: np.ndarray) -> np.ndarray:
    alpha = np.full(channel.shape, 255, dtype=np.uint8)
    return np.dstack([channel, channel, channel, alpha])


def _output(path: Path, suffix: str, ext: str = ".png") -> Path:
    return path.with_name(f"{path.stem}{suffix}{ext}")


def _suffixes(processor: str, output_suffixes: dict[str, str] | None = None) -> dict[str, str]:
    suffixes = dict(DEFAULT_OUTPUT_SUFFIXES[processor])
    if output_suffixes:
        for key, suffix in output_suffixes.items():
            if key in suffixes:
                suffixes[key] = str(suffix)
    return suffixes


def split_color_alpha(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("SplitColorAlphaProcessor", output_suffixes)
    arr = _load_rgba(path)
    rgb = np.dstack([arr[:, :, 0], arr[:, :, 1], arr[:, :, 2], np.full(arr[:, :, 3].shape, 255, dtype=np.uint8)])
    alpha = _gray(arr[:, :, 3])
    return [_save_rgba(rgb, _output(path, suffixes["rgb"], ext)), _save_rgba(alpha, _output(path, suffixes["alpha"], ext))]


def split_rgba(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("SplitRGBAProcessor", output_suffixes)
    arr = _load_rgba(path)
    outputs = []
    for index, key in enumerate(["r", "g", "b", "a"]):
        outputs.append(_save_rgba(_gray(arr[:, :, index]), _output(path, suffixes[key], ext)))
    return outputs


def merge_rgba(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("MergeRGBAProcessor", output_suffixes)
    alpha_path = _output(path, "_a", path.suffix)
    if not alpha_path.exists():
        raise FileNotFoundError(f"Alpha image not found: {alpha_path}")
    rgb = _load_rgba(path)
    with Image.open(alpha_path) as image:
        alpha_image = image.convert("RGBA")
        if alpha_image.size != (rgb.shape[1], rgb.shape[0]):
            alpha_image = alpha_image.resize((rgb.shape[1], rgb.shape[0]), Image.Resampling.LANCZOS)
        alpha = np.array(alpha_image, dtype=np.uint8)
    result = np.dstack([rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2], alpha[:, :, 0]])
    return [_save_rgba(result, _output(path, suffixes["merged"], ext))]


def xy_normal_map(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("XYNormalMapProcessor", output_suffixes)
    arr = _load_rgba(path).astype(np.float32) / 255.0
    nx = arr[:, :, 0] * 2.0 - 1.0
    ny = arr[:, :, 1] * 2.0 - 1.0
    nz = np.sqrt(np.maximum(0.0, 1.0 - nx * nx - ny * ny))
    out = np.dstack([
        np.clip(nx * 0.5 + 0.5, 0.0, 1.0) * 255.0,
        np.clip(ny * 0.5 + 0.5, 0.0, 1.0) * 255.0,
        np.clip(nz * 0.5 + 0.5, 0.0, 1.0) * 255.0,
        np.full(nx.shape, 255.0),
    ])
    return [_save_rgba(out, _output(path, suffixes["normal"], ext))]


def direct_convert(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("DirectConvertProcessor", output_suffixes)
    arr = _load_rgba(path)
    output = _output(path, suffixes["converted"], ext)
    if output.resolve() == path.resolve():
        output = _output(path, "_converted", ext)
    return [_save_rgba(arr, output)]


def direct_invert(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("DirectinvertProcessor", output_suffixes)
    arr = _load_rgba(path).astype(np.float32) / 255.0
    inv = 1.0 - arr[:, :, :3]
    z = inv[:, :, 2]
    inv[:, :, 2] = np.where(z > 0.0, np.sqrt(z), 1.0)
    out = np.dstack([inv[:, :, 0] * 255.0, inv[:, :, 1] * 255.0, inv[:, :, 2] * 255.0, np.full(z.shape, 255.0)])
    return [_save_rgba(out, _output(path, suffixes["inverted"], ext))]


def df_nrm(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("DF_NRM", output_suffixes)
    arr = _load_rgba(path)
    metal = _gray(arr[:, :, 3])
    rou = _gray(arr[:, :, 2])
    normal = np.dstack([arr[:, :, 0], arr[:, :, 1], np.full(arr[:, :, 2].shape, 255, dtype=np.uint8), np.full(arr[:, :, 3].shape, 255, dtype=np.uint8)])
    return [
        _save_rgba(metal, _output(path, suffixes["metal"], ext)),
        _save_rgba(rou, _output(path, suffixes["roughness"], ext)),
        _save_rgba(normal, _output(path, suffixes["normal"], ext)),
    ]


def abi_orn(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("ABI_ORN", output_suffixes)
    arr = _load_rgba(path)
    rou = _gray(arr[:, :, 1])
    ao = _gray(arr[:, :, 0])
    normal = np.dstack([arr[:, :, 3], arr[:, :, 2], np.full(arr[:, :, 2].shape, 128, dtype=np.uint8), np.full(arr[:, :, 3].shape, 255, dtype=np.uint8)])
    return [
        _save_rgba(rou, _output(path, suffixes["roughness"], ext)),
        _save_rgba(ao, _output(path, suffixes["ao"], ext)),
        _save_rgba(normal, _output(path, suffixes["normal"], ext)),
    ]


def df_mra(path: Path, ext: str = ".png", output_suffixes: dict[str, str] | None = None) -> list[Path]:
    suffixes = _suffixes("DF_MRA", output_suffixes)
    arr = _load_rgba(path)
    met_path = _save_rgba(_gray(arr[:, :, 0]), _output(path, suffixes["metal"], ext))
    rou_path = _save_rgba(_gray(arr[:, :, 1]), _output(path, suffixes["roughness"], ext))
    ao_path = _save_rgba(_gray(arr[:, :, 2]), _output(path, suffixes["ao"], ext))
    return [met_path, rou_path, ao_path]


ProcessorFn = Callable[[Path, str, dict[str, str] | None], list[Path]]

GAME2PBR_PROCESSORS: dict[str, ProcessorFn] = {
    "SplitColorAlphaProcessor": split_color_alpha,
    "SplitRGBAProcessor": split_rgba,
    "SplitAllChannelsProcessor": split_rgba,
    "MergeRGBAProcessor": merge_rgba,
    "XYNormalMapProcessor": xy_normal_map,
    "BC5XYNormalMapProcessor": xy_normal_map,
    "DirectConvertProcessor": direct_convert,
    "DirectinvertProcessor": direct_invert,
    "DirectInvertProcessor": direct_invert,
    "DF_NRM": df_nrm,
    "DF_MRA": df_mra,
    "ABI_ORN": abi_orn,
}


def _delete_source(path: Path, outputs: list[Path]) -> None:
    output_paths = {output.resolve() for output in outputs}
    if path.exists() and path.resolve() not in output_paths:
        move_to_recycle_bin(path)


def process_game2pbr(input_path: str | Path, processor: str, ext: str = ".png", delete_source: bool = False, output_suffixes: dict[str, str] | None = None) -> ProcessingResult:
    start = time.time()
    path = Path(input_path)
    if processor not in GAME2PBR_PROCESSORS:
        return ProcessingResult(False, input_path=path, processor=processor, error=f"Unknown processor: {processor}")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return ProcessingResult(False, input_path=path, processor=processor, error=f"Unsupported image extension: {path.suffix}")
    try:
        outputs = GAME2PBR_PROCESSORS[processor](path, ext, output_suffixes)
        if delete_source:
            _delete_source(path, outputs)
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(True, input_path=path, outputs=outputs, processor=processor, elapsed_ms=elapsed)
    except Exception as exc:
        elapsed = int((time.time() - start) * 1000)
        return ProcessingResult(False, input_path=path, processor=processor, elapsed_ms=elapsed, error=f"{type(exc).__name__}: {exc}")
