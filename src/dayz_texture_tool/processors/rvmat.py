"""RVMAT 损坏变体：一份材质复制出 _worn / _damage / _destruct 三份。

只动 class Stage3 里的 texture，其他 Stage 一个字都不碰。换行符、缩进、
等号两边的空格、分号后面的内容全部原样保留 —— 原软件在这几处都会改坏文件。
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path

from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.settings import DEFAULT_RVMAT_DAMAGE_TEXTURES, RVMAT_VARIANTS

RVMAT_EXTENSION = ".rvmat"
PROCESSOR = "RVMAT"

# 二值化过的 rvmat（DayZ 编译后的 config）以这四个字节开头，是二进制不是文本。
BINARY_MAGIC = b"\x00raP"

# 找 class Stage3 的开头。\b 让 "class Stage30" 之类不会被误认。
STAGE3_RE = re.compile(r"class\s+Stage3\b\s*\{")
# 一行里的 texture 赋值。整段（连 texture 这个词一起）留在捕获组里，替换时只换引号里
# 那一段 —— 这样等号两边的空格、分号后面的东西都原样不动。
# 引号里允许反斜杠转义："(?:[^"\\]|\\.)*" 会一路吃到真正的收尾引号。用简单
# 的 "[^"]*" 的话，texture="a\"b.paa" 会在中间那个转义引号处断掉，写出
# texture="NEW"b.paa"; 这种半截东西，而且照样报成功。
# 只认双引号：实测 11865 个文件里 0 个用单引号。
TEXTURE_RE = re.compile(r'(\btexture\s*=\s*)"(?:[^"\\]|\\.)*"')

ProgressCallback = Callable[[int, int, str], None]


def replace_stage3_texture(text: str, texture_path: str) -> str:
    """把 class Stage3 里 texture 的值换成 texture_path。

    除了引号里那个路径，输出跟输入逐字符相同：CRLF、Tab 缩进、等号两边的
    空格、分号后面的注释都留着。整段文本上用正则替换，不做 split/join，
    所以行尾的 \\r 没有机会被吃掉。

    找不到 Stage3、Stage3 没闭合、Stage3 里没有 texture，三种都抛 ValueError。
    """
    match = STAGE3_RE.search(text)
    if match is None:
        raise ValueError("this .rvmat has no class Stage3 block")
    # 从 Stage3 的左花括号开始配对计数，找到属于它的右花括号。
    # 原软件靠"行首是 };"判断结束，Stage3 里嵌套 class uvTransform 时会提前退出。
    depth = 0
    closing = -1
    for index in range(match.end() - 1, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                closing = index
                break
    if closing < 0:
        raise ValueError("class Stage3 block is not closed")
    block = text[match.end():closing]
    replaced, count = TEXTURE_RE.subn(lambda found: f'{found.group(1)}"{texture_path}"', block)
    if count == 0:
        raise ValueError("class Stage3 has no texture line")
    return f"{text[:match.end()]}{replaced}{text[closing:]}"


def read_rvmat_text(path: Path) -> tuple[str, str]:
    """读成文本，返回 (文本, 写回时该用的编码名)。

    原软件写死 UTF-8，碰到别的编码直接失败。这里 UTF-8（带不带 BOM 都行）
    优先，认不出按 GBK 试；写回时用同一个编码名，文件不会变形。
    """
    raw = path.read_bytes()
    if raw.startswith(BINARY_MAGIC):
        raise ValueError("this .rvmat is a compiled binary config, not editable text")
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("gbk"), "gbk"


def normalize_texture_path(value: str) -> str:
    """设置里填的路径：去掉两头空白，斜杠统一成反斜杠。"""
    return value.strip().replace("/", "\\")


def variant_output_path(path: Path, suffix: str) -> Path:
    """变体写在原文件旁边，扩展名沿用原文件的写法。"""
    return path.with_name(f"{path.stem}{suffix}{path.suffix}")


def excluded_variant(path: Path, suffixes: Sequence[str]) -> str:
    """这个文件是不是已经是一个变体了？是就返回命中的后缀，否则返回空串。

    len(stem) > len(suffix) 是防一个叫 "_worn.rvmat" 的文件被当成变体。
    """
    stem = path.stem.lower()
    for suffix in suffixes:
        if not suffix:
            continue
        if len(stem) > len(suffix) and stem.endswith(suffix.lower()):
            return suffix
    return ""


def collect_rvmat_files(path: str | Path) -> list[Path]:
    """给一个文件就收下，给一个文件夹就递归扫；只认 .rvmat，别的静默忽略。"""
    root = Path(path)
    if root.is_file():
        return [root] if root.suffix.lower() == RVMAT_EXTENSION else []
    if not root.is_dir():
        return []
    found = [item for item in root.rglob("*") if item.is_file() and item.suffix.lower() == RVMAT_EXTENSION]
    return sorted(found)


def convert_rvmat(
    input_path: str | Path,
    variants: Sequence[str] = RVMAT_VARIANTS,
    damage_textures: Mapping[str, str] | None = None,
) -> ProcessingResult:
    """一份 .rvmat → 最多三份变体，写在原文件旁边，同名直接覆盖。"""
    start = time.time()
    path = Path(input_path)

    def elapsed() -> int:
        return int((time.time() - start) * 1000)

    try:
        if path.suffix.lower() != RVMAT_EXTENSION:
            raise ValueError(f"not a .rvmat file: {path.name}")
        chosen = [suffix for suffix in RVMAT_VARIANTS if suffix in variants]
        if not chosen:
            raise ValueError("no variant selected")
        table = {**DEFAULT_RVMAT_DAMAGE_TEXTURES, **(damage_textures or {})}

        plans: list[tuple[Path, str]] = []
        for suffix in chosen:
            texture = normalize_texture_path(table.get(suffix, ""))
            if not texture:
                raise ValueError(f"no damage texture configured for {suffix}")
            plans.append((variant_output_path(path, suffix), texture))

        text, encoding = read_rvmat_text(path)
        # 三份内容先全部算完再落盘：中途报错不会留下半批文件。
        written = [(output, replace_stage3_texture(text, texture)) for output, texture in plans]
        for output, content in written:
            # newline="" 不能省：默认的 None 会在 Windows 上把每个 \n 翻成 \r\n，
            # 而原文里已经是 \r\n 的行会变成 \r\r\n —— 整个文件报废。
            output.write_text(content, encoding=encoding, newline="")

        return ProcessingResult(
            True,
            input_path=path,
            outputs=[output for output, _ in written],
            processor=PROCESSOR,
            elapsed_ms=elapsed(),
            messages=[", ".join(output.name for output, _ in written)],
        )
    except Exception as exc:
        return ProcessingResult(
            False,
            input_path=path,
            processor=PROCESSOR,
            elapsed_ms=elapsed(),
            error=f"{type(exc).__name__}: {exc}",
        )


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))


def _batch_conflict(path: Path, variants: Sequence[str], inputs: set[str], claimed: dict[str, Path]) -> str:
    """这一份的产物会不会踩到别人？返回非空字符串就是踩到的原因。"""
    outputs = [variant_output_path(path, suffix) for suffix in variants]
    for output in outputs:
        key = _path_key(output)
        if key in inputs:
            return f"Output {output.name} would overwrite another file in this batch."
        owner = claimed.get(key)
        if owner is not None:
            return f"Output {output.name} is already produced by {owner.name}."
    for output in outputs:
        claimed[_path_key(output)] = path
    return ""


def convert_rvmat_files(
    files: Iterable[str | Path],
    variants: Sequence[str] = RVMAT_VARIANTS,
    damage_textures: Mapping[str, str] | None = None,
    excluded_suffixes: Sequence[str] = RVMAT_VARIANTS,
    progress_callback: ProgressCallback | None = None,
) -> BatchResult:
    """整批跑一遍。已经是变体的文件算「跳过」，不算「失败」。"""
    result = BatchResult()
    paths = [Path(item) for item in files]
    hits = [excluded_variant(path, excluded_suffixes) for path in paths]
    # 已经被排除的变体不算输入，所以它不会挡住别人往同名文件写。
    # 实测 2635 个源文件旁边就躺着同名变体，把它们算成输入等于这个功能白做。
    inputs = {_path_key(path) for path, hit in zip(paths, hits) if not hit}
    claimed: dict[str, Path] = {}
    total = len(paths)

    for index, (path, hit) in enumerate(zip(paths, hits), start=1):
        if hit:
            result.add(
                ProcessingResult(
                    False,
                    input_path=path,
                    processor=PROCESSOR,
                    messages=[f"{path.name} already ends with {hit}; it is a variant, not a source."],
                )
            )
        else:
            conflict = _batch_conflict(path, variants, inputs, claimed)
            if conflict:
                result.add(ProcessingResult(False, input_path=path, processor=PROCESSOR, error=conflict))
            else:
                result.add(convert_rvmat(path, variants, damage_textures))
        if progress_callback is not None:
            progress_callback(index, total, path.name)
    return result
