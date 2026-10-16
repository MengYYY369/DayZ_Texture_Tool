"""命令行入口：不启动界面也能跑五个处理流程。

处理层本来就不依赖 Qt，所以这个模块只 import processors / batch / settings / models。
只有 `gui` 子命令才延迟 import app —— 无显示器、没装 Qt 的机器也能用命令行。

三处有意偏离界面：目录一律递归展开；`--delete-source` 默认关；显式 `--mode` 不套后缀
过滤（后缀分发只由 `--auto` 负责）。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, get_type_hints

from dayz_texture_tool.batch import (
    _is_generated_output,
    detect_game2pbr_processor,
    process_game2pbr_auto,
    process_game2pbr_files,
)
from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.processors import game2pbr as game2pbr_processor
from dayz_texture_tool.processors import pbr2dayz, rvmat, smdi, watermark
from dayz_texture_tool.settings import (
    DEFAULT_GAME_OUTPUT_SUFFIXES,
    DEFAULT_SETTINGS_PATH,
    RVMAT_VARIANTS,
    AppSettings,
    load_settings,
)

DEFAULT_PBR_NORMAL = "directx"
DEFAULT_PBR_RESOLUTION = "auto"
DEFAULT_PBR_CO_MODE = "basecolor"
DEFAULT_PBR_SPECULAR = 0.75
DEFAULT_PBR_GLOSSINESS = 1.0

# settings set 只认这几组枚举值，跟设置页里能选的东西一一对应。
SETTINGS_ENUMS: dict[str, set[str]] = {
    "language": {"en", "zh"},
    "theme": {"dark", "light"},
    "pbr_prefix_mode": {"auto", "current_folder", "parent_folder", "filename_prefix", "custom"},
    "game_match_mode": {"exact", "fuzzy"},
    "pbr_match_mode": {"exact", "fuzzy"},
    "last_page": {"game", "pbr", "smdi", "mark", "rvmat", "settings"},
}

VARIANT_NAMES = {"worn": "_worn", "damage": "_damage", "destruct": "_destruct"}

# 内部名字 → 正名。别名只是同一个处理函数的另一种拼法，输出后缀表里只有正名。
MODE_ALIASES = {
    "splitallchannelsprocessor": "SplitRGBAProcessor",
    "bc5xynormalmapprocessor": "XYNormalMapProcessor",
    "directinvertprocessor": "DirectinvertProcessor",
}


class SkipPlan(Exception):
    """规划阶段就能确定「会跳过」，不算失败。"""


@dataclass
class Plan:
    outputs: list[Path] | None = None
    processor: str = ""
    skip: str = ""
    error: str = ""


@dataclass
class Outcome:
    input_path: Path | None
    status: str
    processor: str = ""
    outputs: list[Path] = field(default_factory=list)
    error: str = ""
    messages: list[str] = field(default_factory=list)
    elapsed_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Context:
    settings: AppSettings
    settings_path: Path
    dry_run: bool = False
    strict: bool = False
    quiet: bool = False
    verbose: bool = False
    json_output: bool = False


# --------------------------------------------------------------------------- #
# 参数解析
# --------------------------------------------------------------------------- #


def _global_parser() -> argparse.ArgumentParser:
    # add_help=False：不然每个子命令都会撞 -h。default=SUPPRESS 是关键 ——
    # 子 parser 也带着同一组全局选项，默认值不能把根 parser 已经解析出来的值盖掉。
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--settings", dest="settings_path", metavar="PATH", default=argparse.SUPPRESS, help="use a specific settings.json instead of the default one")
    parser.add_argument("--json", dest="json_output", action="store_true", default=argparse.SUPPRESS, help="print one machine-readable JSON object on stdout")
    parser.add_argument("--quiet", action="store_true", default=argparse.SUPPRESS, help="do not print progress on stderr")
    parser.add_argument("--verbose", action="store_true", default=argparse.SUPPRESS, help="keep progress on stderr even with --json")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=argparse.SUPPRESS, help="plan only; write nothing")
    parser.add_argument("--strict", action="store_true", default=argparse.SUPPRESS, help="exit 1 when nothing succeeded (no effect with --dry-run)")
    return parser


def build_parser() -> argparse.ArgumentParser:
    global_parser = _global_parser()
    parser = argparse.ArgumentParser(
        prog="dayz-texture-tool-cli",
        description="Drive DayZ Texture Tool without the GUI.",
        parents=[global_parser],
    )
    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    game = subparsers.add_parser("game", parents=[global_parser], help="Game2PBR: one source texture in, one to four out")
    game.add_argument("paths", nargs="+", metavar="PATH", help="files or folders")
    game_mode = game.add_mutually_exclusive_group(required=True)
    game_mode.add_argument("--mode", metavar="NAME", help="processor name, e.g. DF_NRM or df-nrm")
    game_mode.add_argument("--auto", action="store_true", help="pick the processor from the filename suffix")
    game.add_argument("--match", choices=["exact", "fuzzy"], default=None, help="only with --auto (default: settings)")
    game.add_argument("--delete-source", action="store_true", help="move sources to the recycle bin (default: off)")
    game.add_argument("--out-suffix", action="append", metavar="KEY=VALUE", default=None, help="override one output suffix (repeatable, only with --mode)")

    pbr = subparsers.add_parser("pbr", parents=[global_parser], help="PBR2DayZ: one group of PBR textures in, up to four out")
    pbr.add_argument("paths", nargs="+", metavar="PATH", help="files or folders")
    pbr.add_argument("--normal", choices=["directx", "opengl"], default=DEFAULT_PBR_NORMAL, help="normal map convention (default: directx)")
    pbr.add_argument("--resolution", choices=["auto", "256", "512", "1024", "2048"], default=DEFAULT_PBR_RESOLUTION, help="output resolution (default: auto)")
    pbr.add_argument("--prefix-mode", choices=["auto", "current_folder", "parent_folder", "filename_prefix", "custom"], default=None, help="how output names are prefixed (default: settings)")
    pbr.add_argument("--custom-prefix", metavar="STR", default=None, help="prefix used by --prefix-mode custom (default: settings)")
    pbr.add_argument("--match", choices=["exact", "fuzzy"], default=None, help="how filenames are classified (default: settings)")
    pbr.add_argument("--co-mode", metavar="STR", default=None, help=f"CO conversion mode (default: {DEFAULT_PBR_CO_MODE})")
    pbr.add_argument("--specular", type=float, default=None, help=f"SMDI specular (default: {DEFAULT_PBR_SPECULAR})")
    pbr.add_argument("--glossiness", type=float, default=None, help=f"SMDI glossiness (default: {DEFAULT_PBR_GLOSSINESS})")
    pbr.add_argument("--paa", action=argparse.BooleanOptionalAction, default=True, help="convert outputs to PAA (default: on)")
    pbr.add_argument("--watermark", action=argparse.BooleanOptionalAction, default=False, help="embed a watermark in the outputs (default: off)")
    pbr.add_argument("--watermark-content", metavar="STR", default=None, help="watermark text (default: settings)")
    pbr.add_argument("--watermark-password", metavar="STR", default=None, help="watermark password (default: settings)")
    pbr.add_argument("--delete-source", action="store_true", help="move sources to the recycle bin (default: off)")

    mark = subparsers.add_parser("watermark", parents=[global_parser], help="Watermark: embed or detect")
    mark.add_argument("paths", nargs="+", metavar="PATH", help="files or folders")
    mark.add_argument("--mode", choices=["embed", "detect"], default="embed", help="what to do (default: embed)")
    mark.add_argument("--content", metavar="STR", default=None, help="watermark text, required for embed (default: settings)")
    mark.add_argument("--password", metavar="STR", default=None, help="watermark password (default: settings)")
    mark.add_argument("--length", type=int, default=None, help="watermark bit length, required for detect (default: settings)")
    mark.add_argument("--overwrite", action="store_true", help="write back over the source file (default: off)")

    smdi = subparsers.add_parser("smdi", parents=[global_parser], help="SMDI: one color texture in, one specular map out")
    smdi.add_argument("paths", nargs="+", metavar="PATH", help="files or folders")
    smdi.add_argument("--specular", type=float, default=None, help="specular power (default: settings)")
    smdi.add_argument("--paa", action=argparse.BooleanOptionalAction, default=True, help="produce .paa instead of .tga (default: on)")

    mats = subparsers.add_parser("rvmat", parents=[global_parser], help="RVMAT: one material in, up to three damage variants out")
    mats.add_argument("paths", nargs="+", metavar="PATH", help="files or folders")
    mats.add_argument("--variants", metavar="LIST", default=None, help="comma separated worn,damage,destruct (default: all three)")
    mats.add_argument("--damage-texture", action="append", metavar="NAME=PATH", default=None, help="override the Stage3 texture of one variant (repeatable)")

    settings_parser = subparsers.add_parser("settings", parents=[global_parser], help="read and write settings.json")
    settings_actions = settings_parser.add_subparsers(dest="settings_action", metavar="ACTION")
    settings_actions.add_parser("path", help="print the settings file path")
    settings_actions.add_parser("list", help="print every setting")
    settings_get = settings_actions.add_parser("get", help="print one setting")
    settings_get.add_argument("key", metavar="KEY", help="dotted key, e.g. pbr_output_suffixes.co")
    settings_set = settings_actions.add_parser("set", help="write one setting")
    settings_set.add_argument("key", metavar="KEY", help="dotted key, e.g. image_to_paa")
    settings_set.add_argument("value", metavar="VALUE", help="JSON value, or a plain string")

    subparsers.add_parser("gui", parents=[global_parser], help="start the graphical interface")

    return parser


# --------------------------------------------------------------------------- #
# 小工具
# --------------------------------------------------------------------------- #


def _flag(args: argparse.Namespace, name: str, default: Any = False) -> Any:
    return getattr(args, name, default)


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _paa_tool_ok(tool_path: str | Path | None) -> bool:
    return bool(tool_path) and Path(tool_path).exists()


def _expand(inputs: list[str], extensions: set[str]) -> tuple[list[Path], list[Path]]:
    """目录递归展开、按扩展名过滤；显式文件原样保留；不存在的路径单独挑出来。"""
    files: list[Path] = []
    missing: list[Path] = []
    for raw in inputs:
        path = Path(raw)
        if path.is_dir():
            files.extend(sorted(item for item in path.rglob("*") if item.is_file() and item.suffix.lower() in extensions))
        elif path.is_file():
            files.append(path)
        else:
            missing.append(path)
    return files, missing


def _safe_plan(planner: Callable[[Any], tuple[list[Path], str]], item: Any) -> Plan:
    try:
        outputs, processor = planner(item)
        return Plan(outputs=list(outputs), processor=processor)
    except SkipPlan as exc:
        return Plan(skip=str(exc))
    except Exception as exc:
        return Plan(error=f"{type(exc).__name__}: {exc}")


def _conflicts(labels: list[str], plans: list[Plan], inputs: set[str]) -> dict[int, str]:
    """这一批里谁的产物会踩到别人？返回 {下标: 原因}。规则跟 smdi / rvmat 一致。"""
    claimed: dict[str, str] = {}
    blocked: dict[int, str] = {}
    for index, (label, plan) in enumerate(zip(labels, plans)):
        if plan.outputs is None:
            continue
        message = ""
        for output in plan.outputs:
            key = _path_key(output)
            if key in inputs:
                message = f"Output {output.name} would overwrite another input file in this batch."
                break
            owner = claimed.get(key)
            if owner is not None:
                message = f"Output {output.name} is already produced by {owner}."
                break
        if message:
            blocked[index] = message
        else:
            for output in plan.outputs:
                claimed[_path_key(output)] = label
    return blocked


def _outcome_from_result(result: ProcessingResult, fallback_input: Path | None = None) -> Outcome:
    if result.success:
        status = "success"
    elif result.error:
        status = "failed"
    else:
        status = "skipped"
    return Outcome(
        result.input_path or fallback_input,
        status,
        processor=result.processor,
        outputs=list(result.outputs),
        error=result.error,
        messages=list(result.messages),
        elapsed_ms=result.elapsed_ms,
        metadata=dict(result.metadata),
    )


def _missing_outcomes(missing: list[Path], dry_run: bool) -> list[Outcome]:
    return [Outcome(path, "invalid" if dry_run else "failed", error=f"path not found: {path}") for path in missing]


def _assemble(paths: list[Path], blocked: dict[int, str], results: list[ProcessingResult], processor: str = "") -> list[Outcome]:
    """把「被拦下的项」和「真跑出来的结果」按原顺序拼回一份完整清单。"""
    outcomes: list[Outcome] = []
    stream = iter(results)
    for index, path in enumerate(paths):
        if index in blocked:
            outcomes.append(Outcome(path, "failed", processor=processor, error=blocked[index]))
            continue
        result = next(stream, None)
        if result is None:
            outcomes.append(Outcome(path, "failed", processor=processor, error="internal error: missing result"))
        else:
            # PBR 的结果里没有 input_path（一个贴图组才是一个输入），用组目录顶上。
            outcomes.append(_outcome_from_result(result, path))
    return outcomes


def _progress(ctx: Context) -> Callable[[int, int, str], None] | None:
    if ctx.quiet or (ctx.json_output and not ctx.verbose):
        return None

    def report(index: int, total: int, name: str) -> None:
        print(f"[{index}/{total}] {name}", file=sys.stderr, flush=True)

    return report


def _plan_outcomes(paths: list[Path], plans: list[Plan], blocked: dict[int, str]) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for index, path in enumerate(paths):
        plan = plans[index]
        if index in blocked:
            outcomes.append(Outcome(path, "planned-skip", processor=plan.processor, error=blocked[index]))
        elif plan.skip:
            outcomes.append(Outcome(path, "planned-skip", processor=plan.processor, messages=[plan.skip]))
        elif plan.error:
            outcomes.append(Outcome(path, "invalid", processor=plan.processor, error=plan.error))
        else:
            outcomes.append(Outcome(path, "planned", processor=plan.processor, outputs=list(plan.outputs or [])))
    return outcomes


# --------------------------------------------------------------------------- #
# 输出
# --------------------------------------------------------------------------- #

_MARKS = {"success": "OK", "failed": "FAIL", "skipped": "SKIP", "planned": "PLAN", "planned-skip": "SKIP", "invalid": "INVALID"}


def _detail(outcome: Outcome) -> str:
    if outcome.status in ("success", "planned"):
        if outcome.outputs:
            return ", ".join(path.name for path in outcome.outputs)
        return outcome.messages[-1] if outcome.messages else ""
    return outcome.error or (outcome.messages[-1] if outcome.messages else "")


def _summary(outcomes: list[Outcome], elapsed_ms: int, dry_run: bool) -> dict[str, int]:
    if dry_run:
        return {
            "total": len(outcomes),
            "planned": sum(1 for item in outcomes if item.status == "planned"),
            "planned_skip": sum(1 for item in outcomes if item.status == "planned-skip"),
            "invalid": sum(1 for item in outcomes if item.status == "invalid"),
            "elapsed_ms": 0,
        }
    return {
        "total": len(outcomes),
        "succeeded": sum(1 for item in outcomes if item.status == "success"),
        "failed": sum(1 for item in outcomes if item.status == "failed"),
        "skipped": sum(1 for item in outcomes if item.status == "skipped"),
        "elapsed_ms": elapsed_ms,
    }


def _dumps(value: Any) -> str:
    """JSON 一律输出纯 ASCII：管道里的字节不受控制台代码页影响，谁都能直接解析。"""
    return json.dumps(value, indent=2, ensure_ascii=True, default=str)


def _emit(ctx: Context, command: str, outcomes: list[Outcome], elapsed_ms: int) -> None:
    if ctx.json_output:
        payload = {
            "command": command,
            "dry_run": ctx.dry_run,
            "settings_path": str(ctx.settings_path),
            "results": [
                {
                    "input": str(item.input_path) if item.input_path is not None else "",
                    "status": item.status,
                    "processor": item.processor,
                    "outputs": [str(path) for path in item.outputs],
                    "error": item.error,
                    "messages": list(item.messages),
                    "elapsed_ms": item.elapsed_ms,
                    "metadata": item.metadata,
                }
                for item in outcomes
            ],
            "summary": _summary(outcomes, elapsed_ms, ctx.dry_run),
        }
        print(_dumps(payload))
        return
    for item in outcomes:
        print(f"[{_MARKS.get(item.status, item.status)}] {item.input_path} -> {_detail(item)}")
    summary = _summary(outcomes, elapsed_ms, ctx.dry_run)
    print(" · ".join(f"{key}={value}" for key, value in summary.items()))


def _exit_code(outcomes: list[Outcome], strict: bool, dry_run: bool) -> int:
    if dry_run:
        return 1 if any(item.status == "invalid" for item in outcomes) else 0
    if any(item.status == "failed" for item in outcomes):
        return 1
    if strict and not any(item.status == "success" for item in outcomes):
        return 1
    return 0


# --------------------------------------------------------------------------- #
# game
# --------------------------------------------------------------------------- #


def _resolve_game_mode(name: str, parser: argparse.ArgumentParser) -> str:
    canonical = MODE_ALIASES.get(name.strip().lower(), name.strip())
    if canonical in DEFAULT_GAME_OUTPUT_SUFFIXES:
        return canonical
    normalized = canonical.upper().replace("-", "_")
    matches = [mode for mode in DEFAULT_GAME_OUTPUT_SUFFIXES if mode.upper().replace("-", "_") == normalized]
    if len(matches) == 1:
        return matches[0]
    parser.error(f"unknown --mode {name!r}; known modes: {', '.join(DEFAULT_GAME_OUTPUT_SUFFIXES)}")


def _apply_out_suffix(base: dict[str, str], pairs: list[str], processor: str, parser: argparse.ArgumentParser) -> dict[str, str]:
    valid = set(DEFAULT_GAME_OUTPUT_SUFFIXES.get(processor, {}))
    for pair in pairs:
        key, separator, value = pair.partition("=")
        key = key.strip()
        if not separator or not key:
            parser.error(f"--out-suffix expects KEY=VALUE, got {pair!r}")
        if key not in valid:
            parser.error(f"--out-suffix {key!r} is not a slot of {processor}; valid slots: {', '.join(sorted(valid))}")
        base[key] = value
    return base


def _command_game(ctx: Context, args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Outcome]:
    if args.auto and args.out_suffix:
        parser.error("--out-suffix cannot be combined with --auto")
    if not args.auto and args.match is not None:
        parser.error("--match requires --auto")

    files, missing = _expand(args.paths, game2pbr_processor.SUPPORTED_EXTENSIONS)
    if args.auto:
        match_mode = args.match or ctx.settings.game_match_mode
        suffix_map = ctx.settings.game_suffixes
        output_suffix_map = ctx.settings.game_output_suffixes

        def planner(path: Path) -> tuple[list[Path], str]:
            if path.suffix.lower() not in game2pbr_processor.SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported image extension: {path.suffix}")
            found = detect_game2pbr_processor(path, suffix_map, match_mode)
            if found is None:
                raise SkipPlan(f"Skipped {path.name}: no matching suffix.")
            if _is_generated_output(path, found, output_suffix_map):
                raise SkipPlan(f"Skipped {path.name}: generated output suffix.")
            suffixes = output_suffix_map.get(found, {}) if output_suffix_map else None
            return game2pbr_processor.plan_outputs(found, path, suffixes), found

        plans = [_safe_plan(planner, path) for path in files]
        blocked = _conflicts([path.name for path in files], plans, {_path_key(path) for path in files})
        if ctx.dry_run:
            outcomes = _plan_outcomes(files, plans, blocked)
        else:
            progress = _progress(ctx)
            outcomes = []
            for index, path in enumerate(files):
                if index in blocked:
                    outcomes.append(Outcome(path, "failed", error=blocked[index]))
                elif plans[index].error:
                    outcomes.append(Outcome(path, "failed", error=plans[index].error))
                else:
                    batch = process_game2pbr_auto(path, suffix_map, match_mode, args.delete_source, output_suffix_map, None)
                    if batch.results:
                        outcomes.append(_outcome_from_result(batch.results[0]))
                    else:
                        outcomes.append(Outcome(path, "skipped", messages=["No image file found."]))
                if progress is not None:
                    progress(index + 1, len(files), path.name)
    else:
        processor = _resolve_game_mode(args.mode, parser)
        output_suffixes = dict(ctx.settings.game_output_suffixes.get(processor, DEFAULT_GAME_OUTPUT_SUFFIXES.get(processor, {})))
        if args.out_suffix:
            output_suffixes = _apply_out_suffix(output_suffixes, args.out_suffix, processor, parser)
        suffixes_arg = output_suffixes or None

        def planner(path: Path) -> tuple[list[Path], str]:
            if path.suffix.lower() not in game2pbr_processor.SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported image extension: {path.suffix}")
            return game2pbr_processor.plan_outputs(processor, path, suffixes_arg), processor

        plans = [_safe_plan(planner, path) for path in files]
        blocked = _conflicts([path.name for path in files], plans, {_path_key(path) for path in files})
        if ctx.dry_run:
            outcomes = _plan_outcomes(files, plans, blocked)
        else:
            allowed = [path for index, path in enumerate(files) if index not in blocked]
            batch = process_game2pbr_files(allowed, processor, delete_source=args.delete_source, output_suffixes=suffixes_arg, progress_callback=_progress(ctx))
            outcomes = _assemble(files, blocked, batch.results, processor)

    outcomes.extend(_missing_outcomes(missing, ctx.dry_run))
    return outcomes


# --------------------------------------------------------------------------- #
# pbr
# --------------------------------------------------------------------------- #


def _pbr_params(ctx: Context, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "normal_type": args.normal,
        "resolution": args.resolution,
        "co_mode": args.co_mode or DEFAULT_PBR_CO_MODE,
        "specular": DEFAULT_PBR_SPECULAR if args.specular is None else args.specular,
        "glossiness": DEFAULT_PBR_GLOSSINESS if args.glossiness is None else args.glossiness,
        "make_paa": args.paa,
        "image_to_paa": ctx.settings.image_to_paa,
        "delete_source": args.delete_source,
        "output_suffixes": ctx.settings.pbr_output_suffixes,
        "add_watermark": args.watermark,
        "watermark_content": args.watermark_content if args.watermark_content is not None else ctx.settings.watermark_content,
        "watermark_password": args.watermark_password if args.watermark_password is not None else ctx.settings.watermark_password,
    }


def _pbr_usable(group: pbr2dayz.PBRGroup) -> bool:
    return any(tex_type in group.textures for tex_type in ("basecolor", "normal", "roughness", "ao"))


def _command_pbr(ctx: Context, args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Outcome]:
    files, missing = _expand(args.paths, pbr2dayz.IMAGE_EXTENSIONS)
    if files:
        try:
            root = pbr2dayz.root_context_for_files(files)
        except ValueError:
            parser.error("input paths span multiple drives; PBR grouping needs one common root folder")
        match_mode = args.match or ctx.settings.pbr_match_mode
        prefix_mode = args.prefix_mode or ctx.settings.pbr_prefix_mode
        custom_prefix = args.custom_prefix if args.custom_prefix is not None else ctx.settings.pbr_custom_prefix
        groups = pbr2dayz.scan_pbr_paths(files, root, ctx.settings.pbr_suffixes, match_mode, prefix_mode, custom_prefix)
    else:
        groups = []

    output_suffixes = ctx.settings.pbr_output_suffixes

    def planner(group: pbr2dayz.PBRGroup) -> tuple[list[Path], str]:
        if not _pbr_usable(group):
            raise SkipPlan(f"Skipped {group.prefix}: no convertible textures.")
        return pbr2dayz.plan_group_outputs(group, output_suffixes), "PBR2DayZ"

    labels = [f"{group.directory}\\{group.prefix}" for group in groups]
    plans = [_safe_plan(planner, group) for group in groups]
    inputs = {_path_key(path) for group in groups for path in group.textures.values()}
    blocked = _conflicts(labels, plans, inputs)

    if ctx.dry_run:
        outcomes: list[Outcome] = []
        for index, group in enumerate(groups):
            plan = plans[index]
            if index in blocked:
                outcomes.append(Outcome(group.directory, "planned-skip", processor=plan.processor, error=blocked[index]))
            elif plan.skip:
                outcomes.append(Outcome(group.directory, "planned-skip", processor=plan.processor, messages=[plan.skip]))
            elif plan.error:
                outcomes.append(Outcome(group.directory, "invalid", processor=plan.processor, error=plan.error))
            else:
                outcomes.append(Outcome(group.directory, "planned", processor=plan.processor, outputs=list(plan.outputs or [])))
    else:
        params = _pbr_params(ctx, args)
        progress = _progress(ctx)
        results: list[ProcessingResult] = []
        for index, group in enumerate(groups):
            if index not in blocked:
                results.append(pbr2dayz.convert_pbr_group(group, **params))
            if progress is not None:
                progress(index + 1, len(groups), group.prefix)
        outcomes = _assemble([group.directory for group in groups], blocked, results, "PBR2DayZ")

    outcomes.extend(_missing_outcomes(missing, ctx.dry_run))
    return outcomes


# --------------------------------------------------------------------------- #
# watermark
# --------------------------------------------------------------------------- #


def _command_watermark(ctx: Context, args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Outcome]:
    files, missing = _expand(args.paths, watermark.SUPPORTED_WATERMARK_EXTENSIONS)
    password = args.password if args.password is not None else ctx.settings.watermark_password
    if any(path.suffix.lower() == ".paa" for path in files) and not _paa_tool_ok(ctx.settings.image_to_paa):
        parser.error(f"ImageToPAA.exe is required to read .paa files but was not found: {ctx.settings.image_to_paa}")

    if args.mode == "detect":
        length = args.length if args.length is not None else ctx.settings.watermark_length
        if length <= 0:
            parser.error("--length must be greater than 0 for detect (or set watermark_length in settings)")
        batch = watermark.detect_watermark_files(files, password, length, _progress(ctx), ctx.settings.image_to_paa)
        outcomes = [_outcome_from_result(result) for result in batch.results]
    else:
        content = args.content if args.content is not None else ctx.settings.watermark_content
        if not content:
            parser.error("--content is required for embed (or set watermark_content in settings)")
        overwrite = bool(args.overwrite)

        def planner(path: Path) -> tuple[list[Path], str]:
            if path.suffix.lower() not in watermark.SUPPORTED_WATERMARK_EXTENSIONS:
                raise ValueError(f"Unsupported image extension for watermark: {path.suffix}")
            return [watermark.plan_output(path, overwrite)], "Watermark"

        plans = [_safe_plan(planner, path) for path in files]
        # --overwrite 时产物就是输入本身，按「撞到输入」拦下来没有意义。
        blocked = {} if overwrite else _conflicts([path.name for path in files], plans, {_path_key(path) for path in files})
        if ctx.dry_run:
            outcomes = _plan_outcomes(files, plans, blocked)
        else:
            allowed = [path for index, path in enumerate(files) if index not in blocked]
            batch = watermark.add_watermark_files(allowed, content, password, _progress(ctx), ctx.settings.image_to_paa, overwrite)
            outcomes = _assemble(files, blocked, batch.results, "Watermark")

    outcomes.extend(_missing_outcomes(missing, ctx.dry_run))
    return outcomes


# --------------------------------------------------------------------------- #
# smdi
# --------------------------------------------------------------------------- #


def _command_smdi(ctx: Context, args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Outcome]:
    files, missing = _expand(args.paths, smdi.SUPPORTED_SMDI_EXTENSIONS)
    power = args.specular if args.specular is not None else ctx.settings.smdi_specular_power
    make_paa = bool(args.paa)
    if make_paa and not _paa_tool_ok(ctx.settings.image_to_paa):
        parser.error(f"ImageToPAA.exe is required for --paa but was not found: {ctx.settings.image_to_paa}")

    if ctx.dry_run:
        def planner(path: Path) -> tuple[list[Path], str]:
            if path.suffix.lower() not in smdi.SUPPORTED_SMDI_EXTENSIONS:
                raise ValueError(f"Unsupported image extension for SMDI: {path.suffix}")
            return smdi.plan_outputs(path, make_paa), "SMDI"

        plans = [_safe_plan(planner, path) for path in files]
        # 冲突预检用 _planned_outputs：--paa 时那张会被清理掉的 .tga 也算数，跟真跑一致。
        conflict_plans = [
            Plan(outputs=smdi._planned_outputs(path, make_paa)) if plans[index].outputs is not None else plans[index]
            for index, path in enumerate(files)
        ]
        blocked = _conflicts([path.name for path in files], conflict_plans, {_path_key(path) for path in files})
        outcomes = _plan_outcomes(files, plans, blocked)
    else:
        batch = smdi.convert_color_to_smdi_files(files, power, make_paa, ctx.settings.image_to_paa, _progress(ctx))
        outcomes = [_outcome_from_result(result) for result in batch.results]

    outcomes.extend(_missing_outcomes(missing, ctx.dry_run))
    return outcomes


# --------------------------------------------------------------------------- #
# rvmat
# --------------------------------------------------------------------------- #


def _parse_variants(value: str | None, parser: argparse.ArgumentParser) -> list[str]:
    if value is None:
        return list(RVMAT_VARIANTS)
    chosen: list[str] = []
    for raw in value.split(","):
        name = raw.strip().lower().lstrip("_")
        if not name:
            continue
        if name not in VARIANT_NAMES:
            parser.error(f"unknown variant {raw!r}; valid names: {', '.join(VARIANT_NAMES)}")
        suffix = VARIANT_NAMES[name]
        if suffix not in chosen:
            chosen.append(suffix)
    if not chosen:
        parser.error("--variants must select at least one variant")
    return [suffix for suffix in RVMAT_VARIANTS if suffix in chosen]


def _parse_damage_textures(pairs: list[str] | None, parser: argparse.ArgumentParser) -> dict[str, str]:
    textures: dict[str, str] = {}
    for pair in pairs or []:
        name, separator, value = pair.partition("=")
        key = name.strip().lower().lstrip("_")
        if not separator or key not in VARIANT_NAMES:
            parser.error(f"--damage-texture expects NAME=PATH with NAME in {', '.join(VARIANT_NAMES)}, got {pair!r}")
        textures[VARIANT_NAMES[key]] = value
    return textures


def _command_rvmat(ctx: Context, args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Outcome]:
    files, missing = _expand(args.paths, {rvmat.RVMAT_EXTENSION})
    variants = _parse_variants(args.variants, parser)
    damage_textures = dict(ctx.settings.rvmat_damage_textures)
    damage_textures.update(_parse_damage_textures(args.damage_texture, parser))
    excluded = ctx.settings.rvmat_excluded_suffixes

    if ctx.dry_run:
        hits = [rvmat.excluded_variant(path, excluded) for path in files]

        def planner(path: Path) -> tuple[list[Path], str]:
            return [rvmat.variant_output_path(path, suffix) for suffix in variants], rvmat.PROCESSOR

        plans = [_safe_plan(planner, path) for path in files]
        for index, hit in enumerate(hits):
            if hit:
                plans[index] = Plan(processor=rvmat.PROCESSOR, skip=f"{files[index].name} already ends with {hit}; it is a variant, not a source.")
        # 已经是变体的不算输入，所以它不会挡住别人往同名文件写（跟 convert_rvmat_files 一致）。
        inputs = {_path_key(path) for path, hit in zip(files, hits) if not hit}
        blocked = _conflicts([path.name for path in files], plans, inputs)
        outcomes = _plan_outcomes(files, plans, blocked)
    else:
        batch = rvmat.convert_rvmat_files(files, variants, damage_textures, excluded, _progress(ctx))
        outcomes = [_outcome_from_result(result) for result in batch.results]

    outcomes.extend(_missing_outcomes(missing, ctx.dry_run))
    return outcomes


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #


def _display_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _lookup(data: dict[str, Any], key: str) -> Any:
    current: Any = data
    for part in key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise KeyError(key)
        current = current[part]
    return current


def _read_raw_settings(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"error: cannot parse {path}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    if not isinstance(data, dict):
        print(f"error: {path} does not contain a JSON object", file=sys.stderr)
        raise SystemExit(1)
    return data


def _json_or_text(value: str) -> Any:
    try:
        return json.loads(value)
    except ValueError:
        return value


def _coerce_setting(key: str, raw: str, hint: Any, parser: argparse.ArgumentParser) -> Any:
    parsed = _json_or_text(raw)
    if hint is dict or (getattr(hint, "__origin__", None) is dict):
        if not isinstance(parsed, dict):
            parser.error(f"{key} needs a JSON object, got {raw!r}")
        return parsed
    if hint is list or (getattr(hint, "__origin__", None) is list):
        if not isinstance(parsed, list):
            parser.error(f"{key} needs a JSON array, got {raw!r}")
        return parsed
    if hint is bool:
        if not isinstance(parsed, bool):
            parser.error(f"{key} needs true or false, got {raw!r}")
        return parsed
    if hint is int:
        if isinstance(parsed, bool) or not isinstance(parsed, int):
            parser.error(f"{key} needs a whole number, got {raw!r}")
        return parsed
    if hint is float:
        if isinstance(parsed, bool) or not isinstance(parsed, (int, float)):
            parser.error(f"{key} needs a number, got {raw!r}")
        return float(parsed)
    if isinstance(parsed, str):
        value = parsed
    elif parsed is raw:
        value = raw
    else:
        value = str(parsed)
    allowed = SETTINGS_ENUMS.get(key)
    if allowed is not None and value not in allowed:
        parser.error(f"{key} must be one of {', '.join(sorted(allowed))}, got {value!r}")
    return value


def _coerce_leaf(raw: str) -> str:
    parsed = _json_or_text(raw)
    return parsed if isinstance(parsed, str) else raw


def _assign_setting(data: dict[str, Any], key: str, value: Any) -> None:
    parts = key.split(".")
    target = data
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            nested = {}
            target[part] = nested
        target = nested
    target[parts[-1]] = value


def _command_settings(ctx: Context, args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[Outcome]:
    action = getattr(args, "settings_action", None)
    if action is None:
        parser.error("settings needs an action: path, list, get, set")
    if action == "path":
        print(_dumps({"path": str(ctx.settings_path)}) if ctx.json_output else str(ctx.settings_path))
        return []
    if action == "list":
        data = asdict(ctx.settings)
        if ctx.json_output:
            print(_dumps(data))
        else:
            for key, value in data.items():
                print(f"{key} = {_display_value(value)}")
        return []
    if action == "get":
        try:
            value = _lookup(asdict(ctx.settings), args.key)
        except KeyError:
            parser.error(f"unknown settings key: {args.key}")
        print(_dumps(value) if ctx.json_output else _display_value(value))
        return []

    hints = get_type_hints(AppSettings)
    field_name = args.key.split(".")[0]
    if field_name not in hints:
        parser.error(f"unknown settings key: {args.key}")
    data = _read_raw_settings(ctx.settings_path)
    if "." in args.key:
        # 二级键（后缀表、材质覆盖表）的值一律当字符串。
        value = _coerce_leaf(args.value)
    else:
        value = _coerce_setting(field_name, args.value, hints[field_name], parser)
    _assign_setting(data, args.key, value)
    ctx.settings_path.parent.mkdir(parents=True, exist_ok=True)
    ctx.settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    if ctx.json_output:
        print(_dumps({"path": str(ctx.settings_path), "key": args.key, "value": value}))
    else:
        print(f"{args.key} = {_display_value(value)}")
    return []


# --------------------------------------------------------------------------- #
# 入口
# --------------------------------------------------------------------------- #

HANDLERS: dict[str, Callable[[Context, argparse.Namespace, argparse.ArgumentParser], list[Outcome]]] = {
    "game": _command_game,
    "pbr": _command_pbr,
    "watermark": _command_watermark,
    "smdi": _command_smdi,
    "rvmat": _command_rvmat,
    "settings": _command_settings,
}


def main(argv: list[str] | None = None) -> int:
    # 控制台代码页装不下的字符（俄文、emoji 文件名）不该让整个命令崩掉。
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", None)
    if command is None:
        parser.print_help()
        return 2
    if command == "gui":
        from dayz_texture_tool.app import main as app_main

        app_main()
        return 0

    settings_path = Path(_flag(args, "settings_path", None) or DEFAULT_SETTINGS_PATH)
    ctx = Context(
        settings=load_settings(settings_path),
        settings_path=settings_path,
        dry_run=bool(_flag(args, "dry_run")),
        strict=bool(_flag(args, "strict")),
        quiet=bool(_flag(args, "quiet")),
        verbose=bool(_flag(args, "verbose")),
        json_output=bool(_flag(args, "json_output")),
    )
    start = time.time()
    if command == "settings":
        # settings 是配置读写，不走处理结果的信封；stdout 就是那个值本身。
        outcomes = HANDLERS[command](ctx, args, parser)
    else:
        # blind-watermark 第一次用会往 stdout 打一段横幅，会直接搞坏 --json 的契约。
        with contextlib.redirect_stdout(sys.stderr):
            outcomes = HANDLERS[command](ctx, args, parser)
    elapsed_ms = int((time.time() - start) * 1000)
    if command != "settings":
        _emit(ctx, command, outcomes, elapsed_ms)
    return _exit_code(outcomes, ctx.strict, ctx.dry_run)


if __name__ == "__main__":
    sys.exit(main())
