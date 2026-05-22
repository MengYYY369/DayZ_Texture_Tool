from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


APP_DIR = Path.home() / "AppData" / "Roaming" / "DayZ_Texture_Tool"
DEFAULT_SETTINGS_PATH = APP_DIR / "settings.json"

DEFAULT_GAME_SUFFIXES = {
    "SplitColorAlphaProcessor": ["_coloralpha"],
    "SplitRGBAProcessor": ["_rgba"],
    "MergeRGBAProcessor": ["_merge"],
    "XYNormalMapProcessor": ["_xy"],
    "DirectConvertProcessor": ["_convert"],
    "DirectinvertProcessor": ["_invert"],
    "DF_NRM": ["_nrm"],
    "DF_MRA": ["_mra"],
    "ABI_ORN": ["_orn"],
}

DEFAULT_PBR_SUFFIXES = {
    "basecolor": ["basecolor", "base_color", "albedo", "diffuse", "_color", "_d", "_bm_rgb", "_rgb", "_sg_bm_rgb", "_mg_bm_rgb"],
    "normal": ["normal", "_n", "nrm", "nrml", "_mg_orn_n", "_sg_orn_n", "orn_n"],
    "roughness": ["roughness", "rough", "_r", "_mg_orn_rou", "_sg_orn_rou", "_orn_rou", "_rou"],
    "metallic": ["metallic", "metal", "_m", "_sg_bm_alpha", "_mg_bm_alpha", "_bm_alpha", "_alpha", "_b", "_mg_b", "_sg_b"],
    "ao": ["ao", "ambient", "occlusion", "_ao", "_occ", "_mg_orn_ao", "_sg_orn_ao", "_orn_ao"],
}


@dataclass
class AppSettings:
    image_to_paa: str = r"D:\steam\steamapps\common\DayZ Tools\Bin\ImageToPAA\ImageToPAA.exe"
    language: str = "zh"
    game_suffixes: dict[str, list[str]] = field(default_factory=lambda: {key: list(value) for key, value in DEFAULT_GAME_SUFFIXES.items()})
    pbr_suffixes: dict[str, list[str]] = field(default_factory=lambda: {key: list(value) for key, value in DEFAULT_PBR_SUFFIXES.items()})
    game_match_mode: str = "exact"
    pbr_match_mode: str = "fuzzy"


def load_settings(path: str | Path = DEFAULT_SETTINGS_PATH) -> AppSettings:
    settings_path = Path(path)
    if not settings_path.exists():
        return AppSettings()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        merged = {**asdict(AppSettings()), **data}
        settings = AppSettings(**merged)
        settings.game_suffixes = _merge_suffixes(DEFAULT_GAME_SUFFIXES, settings.game_suffixes)
        settings.pbr_suffixes = _merge_suffixes(DEFAULT_PBR_SUFFIXES, settings.pbr_suffixes)
        return settings
    except Exception:
        return AppSettings()


def save_settings(settings: AppSettings, path: str | Path = DEFAULT_SETTINGS_PATH) -> None:
    settings_path = Path(path)
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")


def _merge_suffixes(defaults: dict[str, list[str]], values: dict[str, list[str]]) -> dict[str, list[str]]:
    merged = {key: list(value) for key, value in defaults.items()}
    for key, suffixes in values.items():
        merged[key] = [str(suffix) for suffix in suffixes]
    return merged
