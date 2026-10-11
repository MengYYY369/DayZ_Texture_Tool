# RVMAT Damage Variants — Port `Rvmat-Creator` Into DayZ_Texture_Tool

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a sixth page, **RVMAT**, that takes a batch of `.rvmat` material files and writes a `_worn` / `_damage` / `_destruct` copy of each one next to the original, with `class Stage3`'s texture repointed at a DayZ generic damage texture.

**Architecture:** All text surgery lives in a new leaf processor `src/dayz_texture_tool/processors/rvmat.py` — it takes a path, reads bytes, decides the encoding, swaps one quoted value inside `class Stage3`, and writes. The UI page only collects paths, runs `convert_rvmat` on the single-threaded `FilePage` worker pool, and paints the results. Nothing about the list widget's layout is forked; the one cosmetic addition is a `Slot.placeholder` field so a non-image cell can show a word instead of a file extension.

**Tech Stack:** Python 3.13 (`.venv/Scripts/python.exe` is 3.13.13; `pyproject.toml` requires `>=3.10`, so `Path.write_text(..., newline=)` is available), PySide6, stdlib `re` + `pathlib` only. **No new dependencies.**

**Origin:** this ports the two working parts of `D:/MY/_tools/Rvmat-Creator` (a tkinter app, `src/modules/rvmat_processor.py`) and deliberately leaves its "one-click generate RVMAT from a template" feature behind — that feature duplicates what the SMDI and PBR2DayZ pages already do, and its template lookup was broken in the shipped `main.spec`.

---

## Verified Facts (evidence behind the design)

These were measured against every `.rvmat` file on this machine (`D:/MY`, **12211** files). They are the reason for every non-obvious line in the implementation. Do not "simplify" them away.

1. **12211** `.rvmat` files exist under `D:/MY`. **7437** of them (60.9%) already carry a `_worn` / `_damage` / `_destruct` name suffix. Only **4774** are usable as sources. → the skip list is not a nicety, it is the difference between 4.8k files of work and 12.2k files of mostly-wasted work.
2. **23** of the 12211 are **binary**. They begin with the magic `b"\x00raP"` — a DayZ-compiled (binarised) config, not text. There is no way to edit them. The port must reject them with a readable message instead of dying on a decode error.
3. Of the 12188 text files, **11865** have a `class Stage3` block containing a quoted `texture`, **322** have no `class Stage3` at all, and **1** is the 64-byte scratch garbage described in fact 7 — not a material, so it is not a counter-example to anything. The original tool silently writes a byte-identical copy for those 322 and reports success. → must become a hard error.
4. Stage3's `texture` is spelled **tight** (`texture=`) in **10858** files and **spaced** (`texture = `) in **1007**. The original tool's `if 'texture=' in line:` test misses **all 1007** — it writes an unchanged copy and reports success. That is **8.5% of all convertible files silently producing nothing.** This is the single most important bug to fix.
5. **3805** files hold a procedural value in Stage3, e.g. `texture = "#(argb,8,8,3)color(0,0,0,0,MC)";` — the thing being replaced is not always a path. It is *always* double-quoted, so a quoted-value regex handles both cases uniformly.
6. Line endings: **11294 CRLF**, **894 LF**. The original tool does `line.split('texture=')[0] + f'texture="{p}";'`, which **drops the `\r`** on the one line it rewrites. Reproduced:

   ```
   in:  'class Stage3\r\n{\r\n\ttexture="a.paa";\r\n};\r\n'
   out: 'class Stage3\r\n{\r\n\ttexture="NEW";\n};\r\n'
   ```
   Three CRLF, one bare LF. **94% of real files would be corrupted this way.** Working on the whole string with `re.sub` instead of split/join removes the bug structurally — there is no line list to lose the `\r` in.
7. Encodings: **12187** of the 12188 text files decode as UTF-8; **0** carry a BOM and **0** are GBK-only. The single exception is scratch garbage from an unrelated project, `My_Pbo_Tool/.scratch/c4final/unpacked/scripts/TestMod/tbsL4xw4sF.rvmat` — 64 random bytes, not even the binary magic. It is the "1" that stops fact 3's 11865 + 322 from reaching 12188. → the GBK fallback is defensive insurance, not an evidence-driven requirement. It stays because it costs three lines and the alternative is a crash.
8. **2635** source stems already have a sibling file of the same name plus a variant suffix, and **1899** folders already hold all three variants. The original tool, pointed at such a folder, both **overwrites** the existing `x_worn.rvmat` *and* treats it as a source, manufacturing `x_worn_worn.rvmat`, `x_worn_damage.rvmat`, … — 9 useless files per source. → excluding variants as inputs is a data-safety fix, not a convenience.
9. **2** texture lines carry content after the `;`. The original's `split('texture=')[0] + f'texture="{p}";'` deletes it. Preserving the whole line and swapping only the quoted value keeps it.
10. **0** texture values are single-quoted. **0** texture lines lack a `;`. Only the double-quoted form needs handling.
11. **1** file has two `class Stage3` blocks and **1** file has two `texture` lines inside Stage3. Both are handled by "find the first Stage3 block, replace every texture assignment inside it".
12. A prototype of the exact algorithm below was run over the whole corpus: **11865 converted, 322 rejected, 0 files with a line-ending change**, and a histogram of "how many lines differ" of `{1: 11864, 2: 1}` — i.e. it touches the texture line and nothing else.
13. A real Stage3 block, verbatim (CRLF, Tab-indented, value is procedural):

   ```
   class Stage3
   {
   	texture = "#(argb,8,8,3)color(0,0,0,0,MC)";
   	uvSource = "tex";
   	class uvTransform {
   		aside[] = { 1, 0, 0 };
   		up[] = { 0, 1, 0 };
   		dir[] = { 0, 0, 0 };
   		pos[] = { 0, 0, 0 };
   	};
   };
   ```

   Note the nested `class uvTransform { … };` — the original tool's "leave Stage3 when a line starts with `};`" heuristic would exit on the *inner* `};`. In this corpus the texture line always comes first, so it never bit; brace counting removes the luck.
14. The finished code in Task 1 was run against a 400-file sample of the real corpus: **373 converted, 27 rejected** (24 no-Stage3, 3 binary), **0 outputs with a changed line ending** (305 CRLF sources + 68 LF sources, all byte-identical outside the swapped value), and a "how many lines differ" histogram of exactly **`{1: 1119}`** — 373 files × 3 variants, one changed line each. A real output reads:

    ```
    class Stage3\r\n{\r\n\ttexture="dz\\characters\\data\\generic_worn_mc.paa";\r\n\tuvSource="tex";\r\n	cl…
    ```

    Tab indentation and CRLF intact, only the quoted value swapped.
15. `pyside6-lupdate` must be pointed at the whole `src/dayz_texture_tool/ui` **directory**, not at the individual files a task happened to touch. Both forms report the same `13 new`, so the wrong one looks correct — but the file-list form marks every string in the unlisted files as `<translation type="obsolete">`, `lrelease` silently drops obsolete entries from the `.qm`, and the entire existing Chinese UI reverts to English. Measured on the current tree:

    ```
    $ .venv/Scripts/pyside6-lupdate.exe -recursive -extensions py src/dayz_texture_tool/ui -ts …/dayz_zh_CN.ts
    Found 165 source text(s) (13 new and 152 already existing)
    Same-text heuristic provided 4 translation(s)
    ```

    `152 already existing` is the line that proves the other contexts survived; a much smaller number there means the command was wrong. `lrelease` then reports `Generated 165 translation(s) (161 finished and 4 unfinished)`.

---

## Settled Decisions (user interview)

| # | Decision |
|---|---|
| Q1 | Port feature **A only** (batch-generate damage variants). Feature B ("one-click generate RVMAT from a template") is **not** ported. |
| Q2 | Fix four bugs of the original while porting: (a) tolerate whitespace around `=`; (b) a file with no Stage3 is a hard, explained failure; (c) preserve line endings; (d) detect encoding instead of hard-coding UTF-8. |
| Q3 | The three damage texture paths are **user-editable**, on the Settings page. |
| Q4 | Existing output files are **overwritten** silently, matching the original tool. |
| Q5 | The feature gets its **own sidebar page**, named **RVMAT**. |
| Q6 | One list row = the source file + three result cells. |
| Q7 | Files already ending in `_worn` / `_damage` / `_destruct` are **never used as sources**, but they *are* listed and marked **Skipped** so the user can see why. |
| Q8 | A result cell shows the **variant suffix in large text** and the **output file name in small text**. |
| Q9 | Clicking a cell opens the file with the **system default application** (Notepad, etc.) instead of the image lightbox. |
| Q10 | Stage3 is **fixed** — no "pick which stage" option. |
| Q11 | Outputs are written **next to the source file**. |
| Q12 | Dropping a folder recurses; non-`.rvmat` files are ignored **silently**. |
| Q13 | The three variants are **individually checkable** on the toolbar, all on by default. |
| Q14 | Ship **unit tests** for the parser and the page, in the style of the existing tests. |
| Q15 | The **skip list is editable on the Settings page** (this overrode the earlier "hard-code it" proposal). |

---

## Assumptions The Implementation Depends On

- The three variant suffixes `_worn` / `_damage` / `_destruct` are **fixed** — DayZ's engine looks for those exact names, so they are not configurable. Only the *skip list* is.
- The three checkboxes are **not persisted**. They reset to all-checked on every launch, exactly like the existing `PAA` / `Overwrite` / `Delete source` toggles.
- The damage texture paths default to the original tool's values (`dz\characters\data\generic_{worn,damage,destruct}_mc.paa`) and are DayZ-internal virtual paths, **not** filesystem paths — so the Settings rows get **no "Browse…" button**.
- A `/` typed into a texture path is normalised to `\` (DayZ wants backslashes; humans paste forward slashes). The normalisation happens when the path is *used*, inside `normalize_texture_path` — the Settings field keeps echoing whatever the user typed, slashes and all.
- The result cell's small line is the output file's **stem** (`crate_worn`), not its full name (`crate_worn.rvmat`). The `.rvmat` extension is identical in all three cells and would only steal width from a 70 px cell. This matches `FilePage.output_label`, which every existing page already uses.
- The **skip list is applied when a row is built**, not when it runs. Rows already in the list keep the classification they were built with, so changing the skip list after dropping files does not re-classify them. This is the same snapshot behaviour as every other page's per-row state, and it is a known, accepted limitation rather than an oversight.
- The brace counter in `replace_stage3_texture` is **not** string- or comment-aware: it counts every `{` and `}` between the `class Stage3` opening brace and its match. A `{` or `}` inside a quoted value, or a commented-out `class Stage3 {`, makes the count wrong. In that case the function fails **loudly** (`block is not closed` or `has no texture line`) and writes nothing — it can never silently produce a corrupted file. **0** files in the corpus trigger this.
- An empty texture path for an enabled variant is an error for that file, not a silent skip.
- The new page is appended **after SMDI and before Settings** in the sidebar. The four existing entries are in a deliberate order and inserting into the middle would shuffle the user's muscle memory.
- `Slot.placeholder` is a purely cosmetic field. Every existing caller leaves it empty and keeps today's behaviour (show the file extension).

---

## File Structure

- Create: `src/dayz_texture_tool/processors/rvmat.py`
  The whole feature's logic: text surgery, encoding sniffing, single-file conversion, batch driver, folder scan. No Qt imports, no settings imports beyond the two constants.
- Create: `src/dayz_texture_tool/ui/pages/rvmat.py`
  `RvmatPage(FilePage)`. Toolbar checkboxes, row construction, the skip classification, `process_key`, and the "open with the system default app" override.
- Create: `tests/test_rvmat.py`
  Unit tests for the processor: every quoting/spacing/encoding/line-ending case in Verified Facts, plus the batch-level skip and collision rules.
- Modify: `src/dayz_texture_tool/settings.py`
  Three new constants and two new `AppSettings` fields, plus one merge call in `load_settings`.
- Modify: `src/dayz_texture_tool/ui/items.py`
  One new field on `Slot`.
- Modify: `src/dayz_texture_tool/ui/widgets/row.py`
  One line: honour `slot.placeholder` when there is no thumbnail.
- Modify: `src/dayz_texture_tool/ui/icons.py`
  One entry: an icon for the new nav item.
- Modify: `src/dayz_texture_tool/ui/widgets/sidebar.py`
  Two lines: the nav entry and its `retranslate` entry.
- Modify: `src/dayz_texture_tool/ui/shell.py`
  Two lines: import and register the page in `PAGE_KEYS` + `self.pages`.
- Modify: `src/dayz_texture_tool/ui/pages/settings.py`
  One new `_build_rvmat` section, two new field handlers, and one call each in `__init__` and `_rebuild`.
- Modify: `tests/test_batch_settings.py`
  Cover the two new settings fields' round-trip and defaults.
- Modify: `tests/test_ui_pages.py`
  Cover the new page: drop, skip marking, checkbox wiring, result cells, and the language switch.
- Modify: `src/dayz_texture_tool/ui/translations/dayz_zh_CN.ts` and `.qm`
  New Chinese strings.
- Modify: `docs/功能报告.md`
  A short RVMAT section, matching how the SMDI module was documented.

---

## Success Criteria

- `.venv/Scripts/python.exe -m unittest discover -s tests -q` reports **142 tests, 0 failures** — 90 pre-existing + 38 (`tests/test_rvmat.py`) + 5 (`tests/test_batch_settings.py`) + 9 (`tests/test_ui_pages.py::RvmatPageTests`). The pre-existing 90 all still pass.
- `convert_rvmat` on a CRLF file produces outputs whose bytes differ from the source **only** inside the Stage3 `texture` value — verified by splitting both files with `splitlines(keepends=True)` and asserting exactly one index differs, and by asserting no line ending in the output is a bare `\n` or a doubled `\r\r\n`. A test that only scans for stray newline bytes is **not** sufficient; it passes on `\r\r\n` output (that is how the first version of this plan shipped a file-destroying bug).
- `convert_rvmat` on an LF file produces an output with **no `\r` byte at all** (this is the assertion that catches the Windows `write_text` newline translation).
- A file with `texture = "…"` (spaces) is converted, not copied. A file with `texture="…"` is converted. A file with a procedural `#(argb…)` value is converted.
- A file with no `class Stage3` yields `success=False` with a non-empty `error`, and **all three** candidate output paths are absent — `test_no_stage3_writes_nothing` asserts each of `crate_worn.rvmat`, `crate_damage.rvmat` and `crate_destruct.rvmat` individually, not just the first.
- A file whose name already ends with a skip-list suffix yields `success=False` with an **empty** `error` (i.e. counted as skipped) and no output. This rule lives in `convert_rvmat_files`, which is where a batch has a skip concept; `convert_rvmat` on a single file has no skip rule and will convert a `_worn` file if it is called directly.
- A binary `.rvmat` beginning with `\x00raP` yields a readable error and no output. Binaries that *do not* start with that magic are not specially detected — they fall out as a decode error or as `no class Stage3`.
- An existing `x_worn.rvmat` is overwritten when `x.rvmat` is converted, and is **not** itself converted.
- The RVMAT page appears in the sidebar; its three checkboxes gate which variants are written; its rows always render **exactly three** result cells, and an unchecked variant's cell stays an empty slot rather than disappearing.
- Switching the interface language to Chinese renders the new page's title, action button, empty-state text and mode line in Chinese, with no English left over.
- `python -c "import dayz_texture_tool.settings"` still works with no import cycle.

---

## Known Environment Limits (do not misreport)

- Baseline before starting: **90 tests, all passing**, ~3.3 s (`.venv/Scripts/python.exe -m unittest discover -s tests -q`). `pytest` is **not installed** in `.venv` — do not write pytest-style tests or run `pytest`.
- The UI tests need `QT_QPA_PLATFORM=offscreen`, set at the top of `tests/test_ui_pages.py` **before** PySide6 is imported.
- Translation tooling lives at `.venv/Scripts/pyside6-lupdate.exe` and `.venv/Scripts/pyside6-lrelease.exe`.
- No `.rvmat` sample corpus is committed to the repo. Tests build their fixtures as strings in `tempfile.TemporaryDirectory()`.
- The 12211-file corpus under `D:/MY` is the user's own data. Do **not** run the finished feature over it, and do not write anything into `D:/MY` while testing.

---

## Task 1: The RVMAT Processor

**Files:**
- Create: `src/dayz_texture_tool/processors/rvmat.py`
- Create: `tests/test_rvmat.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_rvmat.py`. Every case in `Verified Facts` gets a test; the ones marked *(fact N)* are the regression tests for the original tool's bugs.

```python
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool.processors.rvmat import (
    BINARY_MAGIC,
    convert_rvmat,
    convert_rvmat_files,
    collect_rvmat_files,
    excluded_variant,
    normalize_texture_path,
    replace_stage3_texture,
    variant_output_path,
)

WORN = r"dz\characters\data\generic_worn_mc.paa"
DAMAGE = r"dz\characters\data\generic_damage_mc.paa"
DESTRUCT = r"dz\characters\data\generic_destruct_mc.paa"

# 一份最小但结构真实的材质：Stage1 有个真路径，Stage3 是程序化颜色，
# Stage4/5 也各有 texture —— 只有 Stage3 那行可以被换掉。
TIGHT = (
    'class Stage1\n{\n\ttexture="a_nohq.paa";\n};\n'
    'class Stage3\n{\n\ttexture="#(argb,8,8,3)color(0,0,0,0,MC)";\n\tuvSource="tex";\n};\n'
    'class Stage5\n{\n\ttexture="a_smdi.paa";\n};\n'
)

SPACED = TIGHT.replace('texture="#(argb', 'texture = "#(argb')


class ReplaceStage3Tests(unittest.TestCase):
    def test_replaces_the_tight_form(self):  # fact 4
        out = replace_stage3_texture(TIGHT, WORN)
        self.assertIn(f'\ttexture="{WORN}";', out)
        self.assertNotIn("#(argb", out)

    def test_replaces_the_spaced_form_and_keeps_the_spacing(self):  # fact 4
        out = replace_stage3_texture(SPACED, WORN)
        self.assertIn(f'\ttexture = "{WORN}";', out)

    def test_leaves_other_stages_alone(self):  # fact 12
        out = replace_stage3_texture(TIGHT, WORN)
        self.assertIn('texture="a_nohq.paa";', out)
        self.assertIn('texture="a_smdi.paa";', out)

    def test_changes_exactly_one_line(self):  # fact 12
        before = TIGHT.splitlines(keepends=True)
        after = replace_stage3_texture(TIGHT, WORN).splitlines(keepends=True)
        self.assertEqual(len(before), len(after))
        self.assertEqual([i for i, (a, b) in enumerate(zip(before, after)) if a != b], [6])

    def test_keeps_crlf(self):  # fact 6
        crlf = TIGHT.replace("\n", "\r\n")
        out = replace_stage3_texture(crlf, WORN)
        self.assertEqual(out.count("\r\n"), crlf.count("\r\n"))
        self.assertNotIn("\n", out.replace("\r\n", ""))
        for line in out.splitlines(keepends=True):
            self.assertTrue(line.endswith("\r\n"), line)

    def test_keeps_content_after_the_semicolon(self):  # fact 9
        text = 'class Stage3\n{\n\ttexture="old.paa"; // keep me\n};\n'
        out = replace_stage3_texture(text, WORN)
        self.assertIn(f'\ttexture="{WORN}"; // keep me', out)

    def test_a_value_with_an_escaped_quote_is_replaced_whole(self):
        # 反斜杠转义的引号。正则必须一路吃到真正的收尾引号，否则会写出
        # texture="NEW"b.paa"; 这种半截东西，还报成功。
        text = 'class Stage3\n{\n\ttexture="a\\"b.paa";\n};\n'
        out = replace_stage3_texture(text, WORN)
        self.assertIn(f'\ttexture="{WORN}";', out)
        self.assertNotIn("b.paa", out)

    def test_does_not_exit_stage3_on_a_nested_class(self):  # fact 13
        # 内层的 }; 必须单独成行 —— 原软件靠“行首是 };”判断 Stage3 结束，会在这里
        # 提前退出，texture 行就落在块外，一个字都不改。写成单行的
        # class uvTransform { aside[]={1,0,0}; }; 是测不出这个修复的：
        # 那种行 strip 之后以 "class" 开头，原软件也会通过。
        text = (
            'class Stage3\n{\n\tclass uvTransform\n\t{\n\t\taside[]={1,0,0};\n\t};\n'
            '\ttexture="old.paa";\n};\n'
        )
        out = replace_stage3_texture(text, WORN)
        self.assertIn(f'texture="{WORN}";', out)

    def test_ignores_a_texture_in_a_later_stage(self):
        text = 'class Stage3\n{\n\ttexture="old.paa";\n};\nclass Stage4\n{\n\ttexture="four.paa";\n};\n'
        out = replace_stage3_texture(text, WORN)
        self.assertIn('texture="four.paa";', out)

    def test_no_stage3_is_an_error(self):  # fact 3
        text = 'class Stage1\n{\n\ttexture="a_nohq.paa";\n};\n'
        with self.assertRaises(ValueError):
            replace_stage3_texture(text, WORN)

    def test_stage3_without_a_texture_is_an_error(self):
        text = 'class Stage3\n{\n\tuvSource="tex";\n};\n'
        with self.assertRaises(ValueError):
            replace_stage3_texture(text, WORN)

    def test_unclosed_stage3_is_an_error(self):
        with self.assertRaises(ValueError):
            replace_stage3_texture('class Stage3\n{\n\ttexture="old.paa";\n', WORN)


class NamingTests(unittest.TestCase):
    def test_output_paths_sit_next_to_the_source(self):  # Q11
        self.assertEqual(
            variant_output_path(Path("D:/mod/data/crate.rvmat"), "_worn"),
            Path("D:/mod/data/crate_worn.rvmat"),
        )

    def test_output_keeps_the_original_extension_case(self):
        self.assertEqual(variant_output_path(Path("crate.RVMAT"), "_worn").name, "crate_worn.RVMAT")

    def test_excluded_variant_matches_case_insensitively(self):  # fact 1
        suffixes = ["_worn", "_damage", "_destruct"]
        self.assertEqual(excluded_variant(Path("crate_WORN.rvmat"), suffixes), "_worn")
        self.assertEqual(excluded_variant(Path("crate.rvmat"), suffixes), "")

    def test_excluded_variant_does_not_match_a_bare_suffix_name(self):
        self.assertEqual(excluded_variant(Path("_worn.rvmat"), ["_worn"]), "")

    def test_normalize_texture_path_flips_slashes(self):
        self.assertEqual(normalize_texture_path("  dz/data/x.paa  "), r"dz\data\x.paa")


class ConvertRvmatTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, name, text, encoding="utf-8", newline=""):
        path = self.root / name
        with open(path, "w", encoding=encoding, newline=newline) as handle:
            handle.write(text)
        return path

    def test_writes_three_files_next_to_the_source(self):  # Q6, Q11
        source = self.write("crate.rvmat", TIGHT)
        result = convert_rvmat(source)
        self.assertTrue(result.success, result.error)
        self.assertEqual([p.name for p in result.outputs], ["crate_worn.rvmat", "crate_damage.rvmat", "crate_destruct.rvmat"])
        for path in result.outputs:
            self.assertTrue(path.exists())
            self.assertEqual(path.parent, self.root)

    def test_each_output_points_at_its_own_texture(self):
        source = self.write("crate.rvmat", TIGHT)
        convert_rvmat(source)
        self.assertIn(WORN, (self.root / "crate_worn.rvmat").read_text(encoding="utf-8"))
        self.assertIn(DAMAGE, (self.root / "crate_damage.rvmat").read_text(encoding="utf-8"))
        self.assertIn(DESTRUCT, (self.root / "crate_destruct.rvmat").read_text(encoding="utf-8"))

    def test_only_the_selected_variants_are_written(self):  # Q13
        source = self.write("crate.rvmat", TIGHT)
        result = convert_rvmat(source, variants=["_damage"])
        self.assertEqual([p.name for p in result.outputs], ["crate_damage.rvmat"])
        self.assertFalse((self.root / "crate_worn.rvmat").exists())

    def test_no_variant_selected_is_an_error(self):  # Q13
        source = self.write("crate.rvmat", TIGHT)
        result = convert_rvmat(source, variants=[])
        self.assertFalse(result.success)
        self.assertTrue(result.error)

    def test_missing_texture_setting_is_an_error(self):  # Q3
        source = self.write("crate.rvmat", TIGHT)
        result = convert_rvmat(source, variants=["_worn"], damage_textures={"_worn": "   "})
        self.assertFalse(result.success)
        self.assertIn("_worn", result.error)
        self.assertFalse((self.root / "crate_worn.rvmat").exists())

    def test_no_stage3_writes_nothing(self):  # Q2b, fact 3
        source = self.write("crate.rvmat", 'class Stage1\n{\n\ttexture="a.paa";\n};\n')
        result = convert_rvmat(source)
        self.assertFalse(result.success)
        self.assertTrue(result.error)
        self.assertEqual(result.outputs, [])
        self.assertFalse((self.root / "crate_worn.rvmat").exists())

    def test_binary_rvmat_is_rejected(self):  # fact 2
        path = self.root / "compiled.rvmat"
        path.write_bytes(BINARY_MAGIC + b"\x00\x00\x00\x00payload")
        result = convert_rvmat(path)
        self.assertFalse(result.success)
        self.assertIn("binary", result.error.lower())

    def test_crlf_survives_the_round_trip(self):  # fact 6
        source = self.write("crate.rvmat", TIGHT.replace("\n", "\r\n"))
        convert_rvmat(source, variants=["_worn"])
        raw = (self.root / "crate_worn.rvmat").read_bytes()
        # 去掉所有 \r\n 之后不该再有落单的 \n（丢过 \r）或 \r（\r\n 被写成了 \r\r\n）
        self.assertEqual(raw.replace(b"\r\n", b"").count(b"\n"), 0)
        self.assertEqual(raw.replace(b"\r\n", b"").count(b"\r"), 0)

    def test_lf_stays_lf(self):  # fact 6
        source = self.write("crate.rvmat", TIGHT)
        convert_rvmat(source, variants=["_worn"])
        self.assertNotIn(b"\r", (self.root / "crate_worn.rvmat").read_bytes())

    def test_utf8_bom_is_preserved(self):
        source = self.write("crate.rvmat", TIGHT, encoding="utf-8-sig")
        convert_rvmat(source)
        self.assertTrue((self.root / "crate_worn.rvmat").read_bytes().startswith(b"\xef\xbb\xbf"))

    def test_gbk_file_is_read_and_written_back_as_gbk(self):  # Q2d, fact 7
        # 中文放在 Stage3 外面 —— 放在里面就会被替换掉，测不出编码。
        text = 'class Stage1\n{\n\ttexture="旧的.paa";\n};\nclass Stage3\n{\n\ttexture="x.paa";\n};\n'
        source = self.write("crate.rvmat", text, encoding="gbk")
        result = convert_rvmat(source, variants=["_worn"])
        self.assertTrue(result.success, result.error)
        raw = (self.root / "crate_worn.rvmat").read_bytes()
        self.assertIn("旧的".encode("gbk"), raw)

    def test_an_existing_output_is_overwritten(self):  # Q4
        source = self.write("crate.rvmat", TIGHT)
        (self.root / "crate_worn.rvmat").write_text("stale", encoding="utf-8")
        convert_rvmat(source, variants=["_worn"])
        self.assertIn(WORN, (self.root / "crate_worn.rvmat").read_text(encoding="utf-8"))

    def test_a_non_rvmat_file_is_rejected(self):
        source = self.write("crate.txt", TIGHT)
        result = convert_rvmat(source)
        self.assertFalse(result.success)
        self.assertTrue(result.error)

    def test_custom_texture_paths_are_used(self):  # Q3
        source = self.write("crate.rvmat", TIGHT)
        convert_rvmat(source, variants=["_worn"], damage_textures={"_worn": "dz/data/mine.paa"})
        self.assertIn(r'texture="dz\data\mine.paa";', (self.root / "crate_worn.rvmat").read_text(encoding="utf-8"))


class CollectTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_a_folder_is_scanned_recursively_and_other_files_are_ignored(self):  # Q12
        (self.root / "sub").mkdir()
        (self.root / "a.rvmat").write_text("x", encoding="utf-8")
        (self.root / "sub" / "b.rvmat").write_text("x", encoding="utf-8")
        (self.root / "sub" / "readme.txt").write_text("x", encoding="utf-8")
        found = collect_rvmat_files(self.root)
        self.assertEqual([p.name for p in found], ["a.rvmat", "b.rvmat"])

    def test_a_single_file_is_taken_as_is(self):
        path = self.root / "a.rvmat"
        path.write_text("x", encoding="utf-8")
        self.assertEqual(collect_rvmat_files(path), [path])

    def test_a_non_rvmat_file_yields_nothing(self):
        path = self.root / "a.txt"
        path.write_text("x", encoding="utf-8")
        self.assertEqual(collect_rvmat_files(path), [])


class BatchTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, name, text=TIGHT):
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_a_variant_is_skipped_not_failed(self):  # Q7, fact 8
        source = self.write("crate.rvmat")
        stale = self.write("crate_worn.rvmat")
        batch = convert_rvmat_files([source, stale])
        self.assertEqual(batch.succeeded, 1)
        self.assertEqual(batch.skipped, 1)
        self.assertEqual(batch.failed, 0)
        self.assertFalse((self.root / "crate_worn_worn.rvmat").exists())

    def test_an_output_that_would_clobber_another_input_fails(self):  # fact 8
        source = self.write("crate.rvmat")
        stale = self.write("crate_worn.rvmat")
        batch = convert_rvmat_files([source, stale], excluded_suffixes=[])
        self.assertEqual(batch.failed, 1)
        # 出错的是第一个文件 —— 它的产物会盖住第二个输入。
        self.assertIn("would overwrite", batch.results[0].error)

    def test_progress_callback_reports_every_file(self):
        source = self.write("crate.rvmat")
        seen = []
        convert_rvmat_files([source], progress_callback=lambda done, total, name: seen.append((done, total, name)))
        self.assertEqual(seen, [(1, 1, "crate.rvmat")])

    def test_batch_reports_success_when_nothing_failed(self):
        batch = convert_rvmat_files([self.write("crate.rvmat")])
        self.assertTrue(batch.success)
        self.assertEqual(len(batch.outputs), 3)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and watch them fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_rvmat -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'dayz_texture_tool.processors.rvmat'`.

- [ ] **Step 3: Write the processor**

Create `src/dayz_texture_tool/processors/rvmat.py`:

```python
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

RVMAT_EXTENSION = ".rvmat"
PROCESSOR = "RVMAT"

# DayZ 引擎按这几个名字找损坏材质，改了就失效，所以写死。
# Task 2 会把这两个常量挪进 settings.py 当单一真相源，然后在这里原样
# re-export —— 所以本文件的其他地方、以及测试，导入路径永远不变。
RVMAT_VARIANTS: tuple[str, ...] = ("_worn", "_damage", "_destruct")
# 每个变体把 class Stage3 的 texture 指向哪张贴图。
DEFAULT_RVMAT_DAMAGE_TEXTURES: dict[str, str] = {
    "_worn": r"dz\characters\data\generic_worn_mc.paa",
    "_damage": r"dz\characters\data\generic_damage_mc.paa",
    "_destruct": r"dz\characters\data\generic_destruct_mc.paa",
}

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
```

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m unittest tests.test_rvmat -q`
Expected: `Ran 38 tests ... OK`. If `test_keeps_crlf`, `test_lf_stays_lf` or `test_changes_exactly_one_line` fails, the implementation is splitting lines or letting `write_text` translate newlines — find it and remove it, do not adjust the test.

- [ ] **Step 5: Commit**

```bash
git add src/dayz_texture_tool/processors/rvmat.py tests/test_rvmat.py
git commit -m "feat: add rvmat damage variant processor"
```

---

## Task 2: Persist The RVMAT Settings

**Files:**
- Modify: `src/dayz_texture_tool/settings.py`
- Modify: `tests/test_batch_settings.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_batch_settings.py` (match the file's existing import block — it already puts `src` on `sys.path`):

```python
class RvmatSettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "settings.json"

    def test_defaults_match_the_dayz_generic_damage_textures(self):  # Q3
        settings = load_settings(self.path)
        self.assertEqual(settings.rvmat_damage_textures["_worn"], r"dz\characters\data\generic_worn_mc.paa")
        self.assertEqual(settings.rvmat_damage_textures["_damage"], r"dz\characters\data\generic_damage_mc.paa")
        self.assertEqual(settings.rvmat_damage_textures["_destruct"], r"dz\characters\data\generic_destruct_mc.paa")

    def test_default_skip_list_is_the_three_variants(self):  # Q7, Q15
        self.assertEqual(load_settings(self.path).rvmat_excluded_suffixes, ["_worn", "_damage", "_destruct"])

    def test_edited_values_survive_a_round_trip(self):  # Q3, Q15
        settings = load_settings(self.path)
        settings.rvmat_damage_textures["_worn"] = r"dz\data\custom.paa"
        settings.rvmat_excluded_suffixes = ["_worn", "_old"]
        save_settings(settings, self.path)

        reloaded = load_settings(self.path)
        self.assertEqual(reloaded.rvmat_damage_textures["_worn"], r"dz\data\custom.paa")
        self.assertEqual(reloaded.rvmat_damage_textures["_damage"], r"dz\characters\data\generic_damage_mc.paa")
        self.assertEqual(reloaded.rvmat_excluded_suffixes, ["_worn", "_old"])

    def test_a_settings_file_written_before_this_feature_still_loads(self):
        self.path.write_text(json.dumps({"language": "zh"}), encoding="utf-8")
        settings = load_settings(self.path)
        self.assertEqual(settings.language, "zh")
        self.assertEqual(settings.rvmat_excluded_suffixes, ["_worn", "_damage", "_destruct"])

    def test_an_emptied_skip_list_stays_empty(self):  # Q15
        self.path.write_text(json.dumps({"rvmat_excluded_suffixes": []}), encoding="utf-8")
        self.assertEqual(load_settings(self.path).rvmat_excluded_suffixes, [])
```

If `tests/test_batch_settings.py` does not already import `json`, `tempfile`, `Path`, `load_settings` and `save_settings`, add them to its import block.

- [ ] **Step 2: Run the tests and watch them fail**

Run: `.venv/Scripts/python.exe -m unittest tests.test_batch_settings -q`
Expected: FAIL — `AttributeError: 'AppSettings' object has no attribute 'rvmat_damage_textures'`.

- [ ] **Step 3: Add the constants and fields**

In `src/dayz_texture_tool/settings.py`, after the existing `DEFAULT_PBR_OUTPUT_SUFFIXES` block, add:

```python
# DayZ 引擎按这几个名字找损坏材质，改了就失效，所以写死。
RVMAT_VARIANTS: tuple[str, ...] = ("_worn", "_damage", "_destruct")

# 每个变体把 class Stage3 的 texture 指向哪张贴图。可以在设置页改。
DEFAULT_RVMAT_DAMAGE_TEXTURES: dict[str, str] = {
    "_worn": r"dz\characters\data\generic_worn_mc.paa",
    "_damage": r"dz\characters\data\generic_damage_mc.paa",
    "_destruct": r"dz\characters\data\generic_destruct_mc.paa",
}

# 名字以这些结尾的文件不当输入（它们已经是变体了）。可以在设置页改。
DEFAULT_RVMAT_EXCLUDED_SUFFIXES: list[str] = list(RVMAT_VARIANTS)
```

In `AppSettings`, after `smdi_specular_power: float = 10.0`, add:

```python
    rvmat_damage_textures: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_RVMAT_DAMAGE_TEXTURES))
    rvmat_excluded_suffixes: list[str] = field(default_factory=lambda: list(DEFAULT_RVMAT_EXCLUDED_SUFFIXES))
```

In `load_settings`, after the `pbr_output_suffixes` merge line, add:

```python
        settings.rvmat_damage_textures = _merge_value_map(DEFAULT_RVMAT_DAMAGE_TEXTURES, settings.rvmat_damage_textures)
```

`rvmat_excluded_suffixes` needs **no** merge: a plain list is taken from the JSON as-is, so a user who empties the field keeps it empty, and a settings file written before this feature falls back to the dataclass default.

- [ ] **Step 4: Point the processor at the new home**

`settings.py` is now the single source of truth. In `src/dayz_texture_tool/processors/rvmat.py`, delete the two constants Task 1 declared locally and import them instead — **keeping exactly the same names**, so no other line in that file changes:

```python
from dayz_texture_tool.models import BatchResult, ProcessingResult
from dayz_texture_tool.settings import DEFAULT_RVMAT_DAMAGE_TEXTURES, RVMAT_VARIANTS
```

The import edge points **processor → settings**, never the other way: `settings.py` must not import anything from `processors/`. Task 1's tests keep passing untouched because they import these names from `dayz_texture_tool.processors.rvmat`, which now re-exports them.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m unittest tests.test_batch_settings tests.test_rvmat -q`
Expected: PASS — 5 new settings tests + the 38 from Task 1, all green.

- [ ] **Step 6: Commit**

```bash
git add src/dayz_texture_tool/settings.py src/dayz_texture_tool/processors/rvmat.py tests/test_batch_settings.py
git commit -m "feat: persist rvmat damage textures and skip list"
```

---

## Task 3: Show A Word Instead Of A File Extension In A Cell

The list paints `slot.path.suffix.upper()[:4]` in a cell that has no thumbnail — for a `.rvmat` that means every cell reads `RVMA`, which tells the user nothing. Add an opt-in override.

**Files:**
- Modify: `src/dayz_texture_tool/ui/items.py`
- Modify: `src/dayz_texture_tool/ui/widgets/row.py`

- [ ] **Step 1: Add the field**

In `src/dayz_texture_tool/ui/items.py`, change `Slot` to:

```python
@dataclass
class Slot:
    """一格小图。path 为 None 表示这一格这次没有东西（灰底槽）。"""

    label: str
    path: Path | None = None
    size_text: str = ""
    missing: bool = False
    placeholder: str = ""  # 读不出缩略图时格子里的大字。空着就显示文件扩展名。
```

- [ ] **Step 2: Honour it in the painter**

In `src/dayz_texture_tool/ui/widgets/row.py`, inside `_draw_cell`, there are **two** places that paint a word into a cell with no thumbnail. Both must honour the new field.

The empty-slot branch:

```python
        painter.drawText(box, Qt.AlignCenter, "—")
```

becomes:

```python
        # 空槽里也认 placeholder：没跑之前那三个格显示 _worn / _damage / _destruct，
        # 没勾的那个 placeholder 是空串，就还是画 "—"。
        painter.drawText(box, Qt.AlignCenter, slot.placeholder or "—")
```

The thumbnail-failed branch:

```python
            painter.drawText(box, Qt.AlignCenter, slot.path.suffix.lstrip(".").upper()[:4] or "?")
```

becomes:

```python
            text = slot.placeholder or slot.path.suffix.lstrip(".").upper()[:4] or "?"
            painter.drawText(box, Qt.AlignCenter, text)
```

Skipping the first one leaves the pre-run cells all showing `—`, which loses the "which three variants am I about to produce" signal the toolbar checkboxes are supposed to give.

- [ ] **Step 3: Check nothing regressed**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -q`
Expected: `Ran 133 tests ... OK` — the pre-existing 90, plus the 38 from Task 1 and the 5 from Task 2. Every existing page leaves `placeholder` empty, so every existing cell paints exactly as before.

- [ ] **Step 4: Commit**

```bash
git add src/dayz_texture_tool/ui/items.py src/dayz_texture_tool/ui/widgets/row.py
git commit -m "feat: let a list cell show a placeholder word"
```

---

## Task 4: The RVMAT Page

**Files:**
- Create: `src/dayz_texture_tool/ui/pages/rvmat.py`
- Modify: `src/dayz_texture_tool/ui/icons.py`
- Modify: `src/dayz_texture_tool/ui/widgets/sidebar.py`
- Modify: `src/dayz_texture_tool/ui/shell.py`

- [ ] **Step 1: Add the nav icon**

In `src/dayz_texture_tool/ui/icons.py`, add one entry to `ICON_NAMES` next to `"smdi"`:

```python
    "rvmat": "ph.swatches",
```

(`ph.swatches` is a palette/material icon. Verified to resolve in the installed `qtawesome`; if it ever stops resolving, `ph.palette` is the fallback.)

- [ ] **Step 2: Register the nav item**

In `src/dayz_texture_tool/ui/widgets/sidebar.py`, add `("rvmat", "rvmat", self.tr("RVMAT"))` to the end of the nav-item list literal — **after** the `smdi` entry and **before** the `addStretch(1)` — and add `self._items["rvmat"].setText(self.tr("RVMAT"))` to `retranslate()` alongside the other entries.

- [ ] **Step 3: Register the page**

In `src/dayz_texture_tool/ui/shell.py`:

```python
from .pages.rvmat import RvmatPage
```

Change `PAGE_KEYS` to:

```python
PAGE_KEYS = ("game", "pbr", "mark", "smdi", "rvmat", "settings")
```

and add to the `self.pages` dict:

```python
            "rvmat": RvmatPage(self.settings),
```

- [ ] **Step 4: Write the page**

Create `src/dayz_texture_tool/ui/pages/rvmat.py`:

```python
"""RVMAT：一份材质复制出三份损坏变体。"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ...models import ProcessingResult
from ...processors.rvmat import RVMAT_VARIANTS, collect_rvmat_files, convert_rvmat, excluded_variant
from ..items import PENDING, SKIPPED, Item, Slot
from ..widgets.toolbar import Toggle
from .file_page import FilePage


class RvmatPage(FilePage):
    page_key = "rvmat"

    def __init__(self, settings, parent=None) -> None:
        super().__init__(
            settings,
            title="RVMAT",
            action_text="Start",
            in_width=70,
            in_label="Source",
            out_label="Variants",
            empty_title="Drop .rvmat materials here",
            empty_hint="Each material gets a _worn, _damage and _destruct copy.",
            empty_accept="RVMAT",
            parent=parent,
        )

        self.toggles: dict[str, Toggle] = {}
        for suffix in RVMAT_VARIANTS:
            toggle = Toggle(suffix, on=True)
            toggle.toggled.connect(self._on_variants)
            self.toggles[suffix] = toggle
            self.add_toolbar(toggle)
        self.add_toolbar_stretch()
        self.add_toolbar(self.add_button)

        self.set_empty_text(
            self.tr("Drop .rvmat materials here"),
            self.tr("Each material gets a _worn, _damage and _destruct copy."),
            "RVMAT",
        )

    # ---- 工具条 ----

    def variants(self) -> list[str]:
        """当前勾着的变体，顺序固定按引擎那三个来。"""
        return [suffix for suffix in RVMAT_VARIANTS if self.toggles[suffix].isChecked()]

    def _on_variants(self) -> None:
        """勾选框变了，还没跑过的行把右边的空槽重摆一遍。"""
        for item in self.list.items():
            if item.status in (PENDING, SKIPPED) and item.selectable:
                item.outputs = self._empty_slots()
        self.list.view.viewport().update()
        self.refresh()

    def _empty_slots(self) -> list[Slot]:
        """三个格子永远都在，不管勾了几个。

        没勾的那格是空槽（placeholder 留空 → 画 "—"），让人一眼看出这一份不会
        被生成 —— 而不是让格子凭空消失、剩下两格重新排版。Q6 说的是「每行三个
        结果格」，不是「每行 N 个」。

        label 留空：它是画在格子**下方**的那行小字，也就是产物文件名。还没跑
        之前没有产物，那行就该是空的 —— 格子里的大字（placeholder）已经说清楚
        这一格会生成哪个变体了，不必再写一遍。
        """
        chosen = self.variants()
        return [
            Slot(label="", missing=True, placeholder=suffix if suffix in chosen else "")
            for suffix in RVMAT_VARIANTS
        ]

    def mode_text(self) -> str:
        return self.tr("Variants: {list}").format(list=" ".join(self.variants()) or "—")

    def file_filter(self) -> str:
        return self.tr("RVMAT") + " (*.rvmat)"

    # ---- 行 ----

    def build_items(self, paths: list[Path]) -> list[Item]:
        items = []
        for path in paths:
            for found in collect_rvmat_files(path):
                items.append(self._make_item(found))
        return items

    def _make_item(self, path: Path) -> Item:
        item = Item(key=str(path), title=path.name, subtitle=path.parent.name)
        item.size_bottom = self.size_text(path)
        item.inputs = [Slot(label=path.name, path=path, size_text=item.size_bottom)]
        hit = excluded_variant(path, self.settings.rvmat_excluded_suffixes)
        if hit:
            # 已经是变体了，不当输入；列出来是为了让人看见"为什么这行没跑"。
            item.status = SKIPPED
            item.status_note = self.tr("Already a {suffix} variant.").format(suffix=hit)
            item.selectable = False
            item.checked = False
            item.outputs = []
        else:
            item.status = PENDING
            item.outputs = self._empty_slots()
        return item

    @staticmethod
    def _suffix_of(path: Path) -> str:
        stem = path.stem.lower()
        for suffix in RVMAT_VARIANTS:
            if stem.endswith(suffix.lower()):
                return suffix
        return ""

    # ---- 跑 ----

    def process_key(self, key: str) -> ProcessingResult:
        return convert_rvmat(key, self.variants(), self.settings.rvmat_damage_textures)

    def apply_result(self, item: Item, result: ProcessingResult) -> None:
        super().apply_result(item, result)
        if not result.success:
            return
        # 按后缀把产物认回来，而不是直接拿 result.outputs 铺 —— 这样格子永远是三个、
        # 顺序永远一样，跑之前跑之后长一个样。没生成的（没勾的、或那一个失败的）
        # 留空槽。
        made = {self._suffix_of(path): path for path in result.outputs}
        slots: list[Slot] = []
        for suffix in RVMAT_VARIANTS:
            path = made.get(suffix)
            if path is None:
                # 没生成的那格和跑之前长得一模一样：空格子，下方也不写文件名。
                slots.append(Slot(label="", missing=True, placeholder=""))
            else:
                # 大字是变体后缀，下面小字是产物文件名。不塞 size_text：行右边
                # 已经有一列尺寸了，70px 的格子里放不下第三行。
                slots.append(Slot(label=path.stem, path=path, placeholder=suffix))
        item.outputs = slots

    # ---- 点格子 ----

    def open_preview(self, item: Item, index: int) -> None:
        """rvmat 是文本，用系统默认程序打开比弹一个读不出图的窗口有用。"""
        slot = dict(self.preview_slots(item)).get(index)
        if slot is not None and slot.path is not None:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(slot.path)))

    # ---- 语言 ----

    def retranslate(self) -> None:
        self.title_label.setText(self.tr("RVMAT"))
        self.status.set_action_text(self.tr("Start"))
        self.add_button.setText(self.tr("＋ Add ▾"))
        self._add_files_action.setText(self.tr("Add files"))
        self._add_folder_action.setText(self.tr("Add folder"))
        self.set_empty_text(
            self.tr("Drop .rvmat materials here"),
            self.tr("Each material gets a _worn, _damage and _destruct copy."),
            "RVMAT",
        )
        self.refresh()
```

- [ ] **Step 5: Check the app still starts**

Run: `.venv/Scripts/python.exe -c "import os; os.environ['QT_QPA_PLATFORM']='offscreen'; from dayz_texture_tool.ui.shell import PAGE_KEYS, MainWindow; print(PAGE_KEYS)"`
Expected: `('game', 'pbr', 'mark', 'smdi', 'rvmat', 'settings')`, no traceback.

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -q`
Expected: PASS. `tests/test_ui_pages.py::SessionTests` may need its expected page list updated — if it asserts on `PAGE_KEYS`, add `"rvmat"` to the expectation.

- [ ] **Step 6: Commit**

```bash
git add src/dayz_texture_tool/ui/pages/rvmat.py src/dayz_texture_tool/ui/icons.py src/dayz_texture_tool/ui/widgets/sidebar.py src/dayz_texture_tool/ui/shell.py
git commit -m "feat: add rvmat page"
```

---

## Task 5: The Settings Section

**Files:**
- Modify: `src/dayz_texture_tool/ui/pages/settings.py`

- [ ] **Step 1: Add the section builder**

In `src/dayz_texture_tool/ui/pages/settings.py`, add to the import block:

```python
from ...processors.rvmat import RVMAT_VARIANTS
```

Add this method next to `_build_pbr`:

```python
    def _build_rvmat(self, lay: QVBoxLayout) -> None:
        card = self._section(
            lay,
            self.tr("RVMAT"),
            self.tr("Every generated variant points class Stage3 at one of these textures."),
        )

        for index, suffix in enumerate(RVMAT_VARIANTS):
            row = self._row(card, first=index == 0)
            row.addWidget(self._label(suffix, MATCH_W))
            field = flex(Field(self.settings.rvmat_damage_textures.get(suffix, ""), 200), 200)
            field.editingFinished.connect(self._make_damage_texture_handler(suffix, field))
            row.addWidget(field, 1)

        row = self._row(card)
        row.addWidget(self._label(self.tr("Skip suffixes"), MATCH_W))
        field = flex(Field(", ".join(self.settings.rvmat_excluded_suffixes), 200), 200)
        field.editingFinished.connect(self._make_excluded_handler(field))
        row.addWidget(field, 1)
```

No "Browse…" button on the texture rows: those are DayZ-internal virtual paths like `dz\characters\data\generic_worn_mc.paa`, not files on disk.

- [ ] **Step 2: Add the handlers**

Next to the other `_make_*_handler` factories:

```python
    def _make_damage_texture_handler(self, suffix: str, field: Field):
        def handler() -> None:
            self.settings.rvmat_damage_textures[suffix] = field.text().strip()
            self._save()

        return handler

    def _make_excluded_handler(self, field: Field):
        def handler() -> None:
            self.settings.rvmat_excluded_suffixes = parse_suffix_text(field.text())
            self._save()

        return handler
```

`parse_suffix_text` already splits on commas and whitespace and drops empties, which is exactly what a skip list needs.

- [ ] **Step 3: Wire it into both build paths**

`SettingsPage` rebuilds itself from scratch on every language switch, so the section must be added in **both** places:

- in `__init__`, after `self._build_pbr(lay)`: `self._build_rvmat(lay)`
- in `_rebuild`, after `self._build_pbr(lay)`: `self._build_rvmat(lay)`

- [ ] **Step 4: Check**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dayz_texture_tool/ui/pages/settings.py
git commit -m "feat: add rvmat settings section"
```

---

## Task 6: Page Tests

**Files:**
- Modify: `tests/test_ui_pages.py`

- [ ] **Step 1: Add the tests**

Append to `tests/test_ui_pages.py`, matching its existing helpers (`pump`, `wait_for`, `drop_event`, `WindowCase.page`):

```python
SAMPLE_RVMAT = (
    'class Stage1\n{\n\ttexture="a_nohq.paa";\n};\n'
    'class Stage3\n{\n\ttexture="#(argb,8,8,3)color(0,0,0,0,MC)";\n};\n'
)


class RvmatPageTests(WindowCase):
    def make_rvmat(self, name="crate.rvmat", text=SAMPLE_RVMAT):
        path = Path(self.tmp.name) / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_dropping_a_material_adds_a_row_with_three_empty_slots(self):  # Q6
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        item = page.list.items()[0]
        self.assertEqual(item.title, "crate.rvmat")
        self.assertEqual([slot.placeholder for slot in item.outputs], ["_worn", "_damage", "_destruct"])
        self.assertTrue(all(slot.missing for slot in item.outputs))

    def test_dropping_a_folder_recurses(self):  # Q12
        root = Path(self.tmp.name) / "mod"
        (root / "sub").mkdir(parents=True)
        (root / "a.rvmat").write_text(SAMPLE_RVMAT, encoding="utf-8")
        (root / "sub" / "b.rvmat").write_text(SAMPLE_RVMAT, encoding="utf-8")
        (root / "sub" / "readme.txt").write_text("x", encoding="utf-8")

        page = self.page("rvmat")
        page.dropEvent(drop_event([root]))
        pump()

        self.assertEqual(sorted(item.title for item in page.list.items()), ["a.rvmat", "b.rvmat"])

    def test_a_variant_file_is_listed_but_marked_skipped(self):  # Q7
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat("crate_worn.rvmat")]))
        pump()
        item = page.list.items()[0]
        self.assertEqual(item.status, SKIPPED)
        self.assertFalse(item.selectable)
        self.assertFalse(item.checked)

    def test_unchecking_a_variant_empties_its_slot_without_removing_it(self):  # Q13, Q6
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.toggles["_destruct"].setChecked(False)
        page._on_variants()
        pump()
        slots = page.list.items()[0].outputs
        # 还是三格 —— 没勾的那格变成空槽，不是整格消失。
        self.assertEqual([slot.placeholder for slot in slots], ["_worn", "_damage", ""])
        # 格子下方那行小字（产物文件名）跑之前是空的。
        self.assertEqual([slot.label for slot in slots], ["", "", ""])
        self.assertTrue(all(slot.missing for slot in slots))

    def test_only_checked_variants_are_written(self):  # Q13
        page = self.page("rvmat")
        page.toggles["_damage"].setChecked(False)
        page.toggles["_destruct"].setChecked(False)
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.start()
        wait_for(page)
        names = sorted(path.name for path in Path(self.tmp.name).glob("crate_*.rvmat"))
        self.assertEqual(names, ["crate_worn.rvmat"])
        # 没勾的两格跑完还是空槽，不是变成两个格。生成了的那格下方写上文件名。
        slots = page.list.items()[0].outputs
        self.assertEqual([slot.placeholder for slot in slots], ["_worn", "", ""])
        self.assertEqual([slot.label for slot in slots], ["crate_worn", "", ""])
        self.assertTrue(slots[1].missing and slots[2].missing)

    def test_result_cells_carry_the_suffix_and_the_file_name(self):  # Q8
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.start()
        wait_for(page)
        slots = page.list.items()[0].outputs
        self.assertEqual([slot.placeholder for slot in slots], ["_worn", "_damage", "_destruct"])
        self.assertEqual([slot.label for slot in slots], ["crate_worn", "crate_damage", "crate_destruct"])
        self.assertTrue(all(slot.path is not None and not slot.missing for slot in slots))

    def test_a_material_without_stage3_lands_in_the_issues_panel(self):  # Q2b
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat("broken.rvmat", 'class Stage1\n{\n\ttexture="a.paa";\n};\n')]))
        pump()
        page.start()
        wait_for(page)
        item = page.list.items()[0]
        self.assertEqual(item.status, FAILED)
        self.assertTrue(item.status_note)
        # 三份候选产物一个都不该落地，不是只看第一份。
        for suffix in ("_worn", "_damage", "_destruct"):
            self.assertFalse((Path(self.tmp.name) / f"broken{suffix}.rvmat").exists())
        # IssuesPanel 不存列表，它直接把内容画成 label —— 只能看标题和可见性。
        # 用 isHidden() 而不是 isVisible()：WindowCase 从来不 win.show()，
        # offscreen 下没显示过的窗口里 isVisible() 恒为 False。现有测试也用 isHidden。
        self.assertFalse(page.issues.isHidden())
        self.assertEqual(page.issues.title.text(), "Issues · 1")

    def test_clicking_a_cell_opens_the_system_default_program(self):  # Q9
        page = self.page("rvmat")
        page.dropEvent(drop_event([self.make_rvmat()]))
        pump()
        page.start()
        wait_for(page)
        with patch("dayz_texture_tool.ui.pages.rvmat.QDesktopServices.openUrl") as opened:
            page._on_slot(page.list.items()[0].key, 1000)
        self.assertTrue(opened.called)
        self.assertIn("crate_worn.rvmat", opened.call_args[0][0].toLocalFile())

    def test_the_page_re_renders_on_a_language_switch(self):
        # 中文那一半要等 Task 7 把 .qm 编出来才能断言 —— 这里只证明切换会重画，
        # 且切回来是干净的英文。完整的中英对照在 Task 7 Step 4。
        page = self.page("rvmat")
        self.assertEqual(page.title_label.text(), "RVMAT")
        self.win.toggle_language()
        pump()
        self.win.toggle_language()
        pump()
        self.assertEqual(page.status.action.text(), "Start")
        self.assertEqual(page.title_label.text(), "RVMAT")
```

`WindowCase` stores its temporary directory on `self.tmp` (and a `Path` version on `self.root`) — confirmed in `tests/test_ui_pages.py`. `FAILED` and `SKIPPED` are already imported at the top of that file; add them to the import from `dayz_texture_tool.ui.items` if not.

- [ ] **Step 2: Run the tests**

Run: `.venv/Scripts/python.exe -m unittest tests.test_ui_pages -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_ui_pages.py
git commit -m "test: cover the rvmat page"
```

---

## Task 7: Translations

**Files:**
- Modify: `src/dayz_texture_tool/ui/translations/dayz_zh_CN.ts`
- Modify: `src/dayz_texture_tool/ui/translations/dayz_zh_CN.qm`

- [ ] **Step 1: Regenerate the `.ts` from source**

Run — and note the argument is the **directory**, not the three changed files (see Verified Fact 15):

```bash
.venv/Scripts/pyside6-lupdate.exe -recursive -extensions py src/dayz_texture_tool/ui -ts src/dayz_texture_tool/ui/translations/dayz_zh_CN.ts
```

Expected:

```
Found 165 source text(s) (13 new and 152 already existing)
Same-text heuristic provided 4 translation(s)
```

`13 new and 152 already existing` is the assertion. Passing the individual files instead — `… ui/pages/rvmat.py ui/pages/settings.py ui/widgets/sidebar.py …` — prints the same `13 new` and looks right, but turns every string in the files you did not list into an obsolete entry, which `lrelease` then drops from the `.qm`. **If the expected line above does not say `152 already existing`, stop and re-run with the directory form.**

You get a new `<context><name>RvmatPage</name>` block, plus new `<message>` entries in the existing `SettingsPage` and `Sidebar` contexts. Every new `<translation>` starts out either empty or heuristic-filled, always with `type="unfinished"`. The `MainWindow` context gains **nothing** — the `shell.py` change is an import, a tuple entry and a dict entry, none of which is a translatable string.

- [ ] **Step 2: Fill in the Chinese**

All **13** new entries, which is what `lupdate` reported:

| Context | source | translation |
|---|---|---|
| `RvmatPage` | `Drop .rvmat materials here` | `把 .rvmat 材质拖进来` |
| `RvmatPage` | `Each material gets a _worn, _damage and _destruct copy.` | `每份材质会复制出 _worn、_damage、_destruct 三份。` |
| `RvmatPage` | `Variants: {list}` | `变体：{list}` |
| `RvmatPage` | `Already a {suffix} variant.` | `已经是 {suffix} 变体了。` |
| `RvmatPage` | `Start` | `开始处理` |
| `RvmatPage` | `＋ Add ▾` | `＋ 添加 ▾` |
| `RvmatPage` | `Add files` | `添加文件` |
| `RvmatPage` | `Add folder` | `添加文件夹` |
| `RvmatPage` | `RVMAT` | `RVMAT` |
| `Sidebar` | `RVMAT` | `RVMAT` |
| `SettingsPage` | `RVMAT` | `RVMAT` |
| `SettingsPage` | `Every generated variant points class Stage3 at one of these textures.` | `生成的每个变体都把 class Stage3 指向这几张贴图之一。` |
| `SettingsPage` | `Skip suffixes` | `跳过后缀` |

Four of the thirteen — `Start`, `＋ Add ▾`, `Add files`, `Add folder` — come back from `lupdate` **already filled in** by its same-text heuristic (it copies the translation over from `GamePage` / `FilePage`, which hold the identical English), but still tagged `type="unfinished"`. The Chinese works at runtime either way; removing the attribute only marks them as reviewed. The other nine are blank and must be written.

The three `RVMAT` rows are the identity translation — they look like no-ops, and skipping them is harmless, because the fallback for a missing translation *is* the English source string, which is already `RVMAT`. Fill them anyway so the `.ts` reads as fully translated; do not be surprised that they change nothing on screen.

`Source` and `Variants` will **not** appear in the `.ts` and never should: `in_label` / `out_label` are plain string literals, not `tr()` calls, and `ListHeader.paintEvent` paints them verbatim. Every existing page behaves this way — leave them alone, and do not "fix" them into `tr()` calls as part of this task.

The repeated English text gets a **separate entry per context** — Qt keys translations by context, not by source text, so `Start` under `RvmatPage` is a different entry from `Start` under `GamePage`. `lupdate` never merges them. Missing one would not crash, but only because of a *runtime* fallback: PySide6's `tr()` walks the class's MRO, so a subclass instance can still reach a base class's context. `RvmatPage` inherits `FilePage`, and `FilePage`'s context does **not** contain `Start` — so `Start` is the one entry that genuinely must be filled in for the Chinese UI to be complete.

- [ ] **Step 3: Compile the `.qm`**

Run:

```bash
.venv/Scripts/pyside6-lrelease.exe src/dayz_texture_tool/ui/translations/dayz_zh_CN.ts -qm src/dayz_texture_tool/ui/translations/dayz_zh_CN.qm
```

Expected: `Generated 165 translation(s) (161 finished and 4 unfinished)`. The 4 unfinished are the ones left as `type="unfinished"`. If the total is much smaller than 165, Step 1 was run against individual files instead of the directory — redo it (Verified Fact 15).

- [ ] **Step 4: Check**

Run: `.venv/Scripts/python.exe -m unittest tests.test_ui_pages -q`
Expected: PASS.

Now add the Chinese half of the language test — it can only be written *now*, because before this step the `.qm` had no `RvmatPage` context and the assertion would have failed:

```python
    def test_language_switch_keeps_the_page_in_english_and_chinese(self):
        page = self.page("rvmat")
        self.assertEqual(page.title_label.text(), "RVMAT")
        self.win.toggle_language()
        pump()
        self.assertEqual(page.status.action.text(), "开始处理")
        self.assertEqual(page.mode_text(), "变体：_worn _damage _destruct")
        self.win.toggle_language()
        pump()
        self.assertEqual(page.status.action.text(), "Start")
        self.assertEqual(page.mode_text(), "Variants: _worn _damage _destruct")
```

Run again: `.venv/Scripts/python.exe -m unittest tests.test_ui_pages -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/dayz_texture_tool/ui/translations/dayz_zh_CN.ts src/dayz_texture_tool/ui/translations/dayz_zh_CN.qm
git commit -m "i18n: translate the rvmat page"
```

---

## Task 8: Documentation And Full Verification

**Files:**
- Modify: `docs/功能报告.md`

- [ ] **Step 1: Document the page**

Add an RVMAT section to `docs/功能报告.md`, matching the shape of the SMDI section: what the page does, where the outputs land, which settings it reads, and which four bugs it fixes relative to `Rvmat-Creator`.

- [ ] **Step 2: Run everything**

Run: `.venv/Scripts/python.exe -m unittest discover -s tests -q`
Expected: `Ran 142 tests ... OK`, zero failures, zero errors — 90 pre-existing + 38 (Task 1) + 5 (Task 2) + 9 (Task 6). A different total means a test was dropped rather than made to pass.

Run: `.venv/Scripts/python.exe -c "import dayz_texture_tool.settings, dayz_texture_tool.processors.rvmat; print('imports ok')"`
Expected: `imports ok`.

- [ ] **Step 3: Commit**

```bash
git add docs/功能报告.md
git commit -m "docs: add rvmat module to feature report"
```

---

## Self-Review

**Spec coverage.** Q1 (feature A only) — Task 1 ports only the processor, and no template/one-click path exists anywhere in the plan. Q2a (whitespace) — `TEXTURE_RE` matches `\s*=\s*` and the test asserts the spacing survives. Q2b (no Stage3) — `replace_stage3_texture` raises, `convert_rvmat` turns it into a non-empty `error`, and `test_no_stage3_writes_nothing` proves none of the three outputs is produced. Q2c (line endings) — no split/join anywhere; `test_crlf_survives_the_round_trip` and `test_changes_exactly_one_line` cover it. Q2d (encoding) — `read_rvmat_text` returns the encoding to write back with. Q3 — `rvmat_damage_textures` in `AppSettings` + the three Settings rows. Q4 — plain `write_text`, covered by `test_an_existing_output_is_overwritten`. Q5 — Task 4's page registration. Q6 (one row = source + **three** result cells) — enforced in both `_empty_slots` and `apply_result`, which each build from `RVMAT_VARIANTS`, so the cell count is three before the run and three after, whatever the checkboxes say. Q7 — `excluded_variant` in both the processor and `_make_item`. Q8 — `Slot.placeholder` + `apply_result`; the small line is the output **stem**, matching `FilePage.output_label`. Q9 — `open_preview`. Q10 — Stage3 is a module constant, no UI. Q11 — `variant_output_path`. Q12 — `collect_rvmat_files`. Q13 — the toolbar `Toggle`s. Q14 — Tasks 1, 2, 6, 7. Q15 — `rvmat_excluded_suffixes` + the Settings row.

**Placeholder scan.** No `TODO`, no `pass  # later`, no unbound names. Every existing-file detail the plan leans on was read out of the repo and pinned down rather than left as "go look it up": `WindowCase.tmp` / `WindowCase.root`, `IssuesPanel.title` + `isHidden()` (not `isVisible()` — `WindowCase` never calls `win.show()`), `WindowCase.page()`, `pump()` / `wait_for()` / `drop_event()`, `StatusBar.action`, `Toggle.isChecked()` / `setChecked()`.

**Type consistency.** `convert_rvmat(input_path, variants, damage_textures)` is called with exactly those three arguments in both `RvmatPage.process_key` and `convert_rvmat_files`. `Slot(label, path, size_text, missing, placeholder)` keeps the existing positional order and appends the new field last, so every existing construction site is untouched. `RVMAT_VARIANTS` is a `tuple` in `settings.py` and is only ever iterated, never mutated; `DEFAULT_RVMAT_EXCLUDED_SUFFIXES` is a separate `list` so the dataclass default is not a shared mutable.

**Scope check.** One processor, one page, one settings section, one new `Slot` field, one changed painter line. No refactor of `FilePage`, no change to any existing page's behaviour, no change to `BatchResult` or `ProcessingResult`.

**Deliberate deviations from the original tool.** (1) The `};`-based Stage3 exit becomes brace counting — the original is right only by luck (fact 13). (2) `line.split('texture=')[0] + …` becomes a quoted-value substitution, which is what preserves the CRLF and any trailing comment (facts 6, 9). (3) `return True` unconditionally becomes a real `ProcessingResult`. (4) `f"{base_name}{suffix}.rvmat"` becomes `path.with_name(...)`, so a `.RVMAT` in the wild keeps its case. (5) The overwrite policy is unchanged (Q4) — but the *skip list* now stops the original's habit of overwriting a sibling variant and then manufacturing nine `x_worn_worn`-style files from it (fact 8). (6) A texture value containing an **escaped quote** (`texture="a\"b.paa"`) is matched whole; the naive `"[^"]*"` form stopped at the escaped quote and wrote `texture="NEW"b.paa";` while reporting success. (7) A **single-quoted** value (`texture='a.paa'`) is now a hard `has no texture line` error instead of a replacement that destroyed the line — **0** files in the corpus use it. (8) A texture line **without** a trailing `;` no longer gets one appended — the original rebuilt the whole line and added it. **0** files in the corpus lack it. (9) The brace counter is **not** string- or comment-aware; a `{` / `}` inside a quoted value makes the file fail **loudly** rather than silently. See Assumptions. (10) A file named `a.worn.rvmat` (dot, not underscore) is **not** recognised as a variant and will be converted into `a.worn_worn.rvmat`; the skip list matches underscore suffixes only, which is what DayZ itself uses. (11) The skip list is snapshotted when a row is built, so editing it after dropping files does not re-classify the rows already on screen.

**Risk called out.** Two traps in this code are load-bearing and both were found by running it, not by reading it:

1. **`output.write_text(content, encoding=encoding, newline="")`** — the `newline=""` is mandatory. `Path.write_text` defaults to `newline=None`, which on Windows translates every `\n` to `\r\n`. The content already contains `\r\n` from the source, so a CRLF file comes out with `\r\r\n` on **every line** — the whole file is destroyed, and a naive `assertNotIn(b"\n", raw.replace(b"\r\n", b""))` test still passes. The `test_lf_stays_lf` case is what catches it: an LF file must stay LF.
2. **`TEXTURE_RE`'s capture group must include the word `texture`.** `r'(\btexture\s*=\s*)"[^"]*"'` and not `r'\btexture(\s*=\s*)"[^"]*"'`. The second form captures only the `=`, so the substitution silently rewrites the line to `\t="dz\…";` — the keyword vanishes and the material is broken. Both forms look equally reasonable on screen.
3. The replacement must go through a **`lambda`**, not a string: `re.sub` treats backslashes in a *string* replacement as escapes, so `r'dz\characters\…'` would raise `re.error: bad escape \c`. Do not "simplify" the lambda into an f-string replacement.

---

## Implementation Notes

Filled in after the work landed. Everything below is a deviation from, or an addition to, what this plan literally says.

**The plan ran clean.** Every task's expected test count matched on the first run — `Ran 38 tests` after Task 1, `Ran 53 tests` after Task 2, `Ran 133 tests` after Tasks 3–5, and the final `Ran 142 tests ... OK` after Task 6. Both dry runs had already shaken out the bugs, so nothing had to be debugged during implementation. The 8 commits:

```
b2d93e9 feat: add rvmat damage variant processor
2459f14 feat: persist rvmat damage textures and skip list
df8f6a9 feat: let a list cell show a placeholder word
f41c248 feat: add rvmat page
55ebfdb feat: add rvmat settings section
fb79a24 test: cover the rvmat page
4203691 i18n: translate the rvmat page
e66292d docs: add rvmat module to feature report
```

**Task 7 replaced a Task 6 test instead of adding one.** Task 6's `test_the_page_re_renders_on_a_language_switch` is a strictly weaker version of Task 7's `test_language_switch_keeps_the_page_in_english_and_chinese` — it was written to survive before the `.qm` had an `RvmatPage` context. Keeping both would have made the total 143 and left two methods asserting the same thing, so Task 7's version overwrites it in place. `test_ui_pages.py` still has 9 RVMAT tests, and the total is still the 142 this plan predicts.

**The working tree was already dirty.** This repo carried a large uncommitted PySide6 migration when the work started (`git status` listed modified `app.py`, `pyproject.toml`, `requirements.txt`, `DayZ_Texture_Tool.spec`, deleted `ui/i18n.py`, `ui/main_window.py`, `tests/test_ui_dragdrop.py`, and dozens of untracked files). Two of the files this plan edits — `src/dayz_texture_tool/settings.py` and `docs/功能报告.md` — were already modified, and staging them necessarily carried their pending changes into the commits above. There is no way to avoid that without interactive `git add -p`, and it was not worth fragmenting the history to dodge. The `e66292d` commit body says so explicitly. **Nothing else in the working tree was touched** — in particular no `git checkout --` was ever run against a dirty file.

**`core.autocrlf` is on.** Every `git add` of a file that has LF endings in the index prints `warning: in the working copy of '<file>', LF will be replaced by CRLF the next time Git touches it`. Harmless — the repo has been in this state for a while.

**The one thing that would silently break the translation step** is already called out in Task 7 Step 1, but it is worth repeating here because the failure mode is invisible: `pyside6-lupdate` must be pointed at the whole `src/dayz_texture_tool/ui` directory. Listing only the changed files still reports `13 new`, still looks right, and still produces a working-looking `.ts` — but it rewrites every string in the files you did not list as `type="obsolete"`, and `lrelease` drops obsolete entries from the `.qm`. The entire Chinese UI silently reverts to English. If you ever regenerate the translations by hand, check that `lupdate` reports `152 already existing`, not `Kept N obsolete entries`.
