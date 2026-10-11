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
