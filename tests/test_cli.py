import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dayz_texture_tool import cli

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"


def write_image(path: Path, size: int = 8, color=(120, 80, 40, 255)) -> None:
    array = np.zeros((size, size, 4), dtype=np.uint8)
    array[:, :] = color
    Image.fromarray(array, "RGBA").save(path)


def write_rvmat(path: Path, texture: str = '#(argb,8,8,3)color(0,0,0,0,MC)') -> None:
    path.write_text(f'class Stage3\n{{\n\ttexture="{texture}";\n\tuvSource="tex";\n}};\n', encoding="utf-8")


def run_cli(*argv) -> tuple[int, str, str]:
    """跑一次 main()，把 stdout / stderr 抓下来。argparse 的 SystemExit 也当成退出码。"""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main([str(item) for item in argv])
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue(), err.getvalue()


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.settings = self.root / "settings.json"

    def work(self, name: str = "work") -> Path:
        folder = self.root / name
        folder.mkdir(exist_ok=True)
        return folder

    def cli(self, *argv) -> tuple[int, str, str]:
        return run_cli("--settings", self.settings, *argv)


class ArgumentParsingTests(CliTestCase):
    def test_no_subcommand_prints_help_and_exits_2(self):
        code, out, err = self.cli()
        self.assertEqual(code, 2)
        self.assertIn("usage:", out)
        self.assertIn("game", out)

    def test_global_flags_survive_before_and_after_the_subcommand(self):
        # 回归：argparse 的 parents 共用会让子 parser 的默认值把根 parser 已解析的值盖掉。
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        before = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", folder)
        after = self.cli("game", "--json", "--dry-run", "--mode", "df-nrm", folder)
        for code, out, _ in (before, after):
            self.assertEqual(code, 0)
            payload = json.loads(out)
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["summary"]["planned"], 1)

    def test_unknown_subcommand_exits_2(self):
        code, _, err = self.cli("nonsense")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)

    def test_game_requires_a_mode_or_auto(self):
        code, _, err = self.cli("game", self.work())
        self.assertEqual(code, 2)
        self.assertIn("--mode", err)

    def test_game_rejects_mode_and_auto_together(self):
        code, _, err = self.cli("game", "--mode", "df-nrm", "--auto", self.work())
        self.assertEqual(code, 2)
        self.assertIn("not allowed with", err)

    def test_unknown_mode_exits_2(self):
        code, _, err = self.cli("game", "--mode", "bogus", self.work())
        self.assertEqual(code, 2)
        self.assertIn("unknown --mode", err)

    def test_mode_names_accept_case_and_hyphen_variants(self):
        folder = self.work()
        write_image(folder / "a.tga")
        for name in ("df-nrm", "DF_NRM", "DF-NRM"):
            code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", name, folder)
            self.assertEqual(code, 0, name)
            self.assertEqual(json.loads(out)["summary"]["planned"], 1, name)

    def test_case_colliding_processor_aliases_resolve_to_the_same_outputs(self):
        folder = self.work()
        write_image(folder / "a.tga")
        canonical, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "SplitRGBAProcessor", folder)
        alias, out2, _ = self.cli("--json", "--dry-run", "game", "--mode", "SplitAllChannelsProcessor", folder)
        self.assertEqual((canonical, alias), (0, 0))
        self.assertEqual(json.loads(out)["results"][0]["outputs"], json.loads(out2)["results"][0]["outputs"])

    def test_out_suffix_is_rejected_with_auto(self):
        code, _, err = self.cli("game", "--auto", "--out-suffix", "co=_x", self.work())
        self.assertEqual(code, 2)
        self.assertIn("--out-suffix cannot be combined with --auto", err)

    def test_out_suffix_rejects_an_unknown_slot(self):
        code, _, err = self.cli("game", "--mode", "df-nrm", "--out-suffix", "nope=_x", self.work())
        self.assertEqual(code, 2)
        self.assertIn("is not a slot of", err)

    def test_out_suffix_rejects_a_malformed_pair(self):
        code, _, err = self.cli("game", "--mode", "df-nrm", "--out-suffix", "co", self.work())
        self.assertEqual(code, 2)
        self.assertIn("KEY=VALUE", err)

    def test_match_flag_is_only_meaningful_with_auto(self):
        code, _, err = self.cli("game", "--mode", "df-nrm", "--match", "fuzzy", self.work())
        self.assertEqual(code, 2)
        self.assertIn("--match requires --auto", err)

    def test_rvmat_rejects_an_unknown_variant(self):
        code, _, err = self.cli("rvmat", "--variants", "worn,bogus", self.work())
        self.assertEqual(code, 2)
        self.assertIn("unknown variant", err)

    def test_damage_texture_rejects_a_malformed_pair(self):
        code, _, err = self.cli("rvmat", "--damage-texture", "worn", self.work())
        self.assertEqual(code, 2)
        self.assertIn("NAME=PATH", err)


class PathExpansionTests(CliTestCase):
    def test_folders_are_expanded_recursively(self):
        folder = self.work()
        nested = folder / "deep"
        nested.mkdir()
        write_image(folder / "a_df_nrm.tga")
        write_image(nested / "b_df_nrm.tga")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"]["total"], 2)

    def test_non_image_files_inside_a_folder_are_ignored(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        (folder / "notes.txt").write_text("skip me", encoding="utf-8")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["summary"]["total"], 1)

    def test_an_explicit_file_with_a_wrong_extension_is_reported_invalid(self):
        folder = self.work()
        notes = folder / "notes.txt"
        notes.write_text("skip me", encoding="utf-8")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", notes)
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["results"][0]["status"], "invalid")
        self.assertEqual(payload["summary"]["invalid"], 1)

    def test_a_missing_path_is_a_failure(self):
        code, out, _ = self.cli("--json", "game", "--mode", "df-nrm", self.root / "nope")
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["results"][0]["status"], "failed")
        self.assertIn("path not found", payload["results"][0]["error"])

    def test_an_empty_folder_succeeds_unless_strict(self):
        folder = self.work()
        self.assertEqual(self.cli("game", "--mode", "df-nrm", folder)[0], 0)
        self.assertEqual(self.cli("--strict", "game", "--mode", "df-nrm", folder)[0], 1)

    def test_strict_does_not_change_a_successful_run(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        self.assertEqual(self.cli("--strict", "game", "--mode", "df-nrm", folder)[0], 0)


class DryRunTests(CliTestCase):
    def test_dry_run_writes_nothing(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        before = sorted(path.name for path in folder.iterdir())
        code, _, _ = self.cli("--dry-run", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(path.name for path in folder.iterdir()), before)

    def test_dry_run_lists_the_planned_outputs(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "planned")
        self.assertTrue(result["outputs"])
        for output in result["outputs"]:
            self.assertFalse(Path(output).exists())

    def test_auto_dry_run_skips_files_without_a_matching_suffix(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        write_image(folder / "b_co.tga")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--auto", folder)
        self.assertEqual(code, 0)
        summary = json.loads(out)["summary"]
        self.assertEqual((summary["planned"], summary["planned_skip"]), (1, 1))

    def test_dry_run_reports_the_three_state_vocabulary(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        notes = folder / "notes.txt"
        notes.write_text("skip me", encoding="utf-8")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", folder, notes)
        self.assertEqual(code, 1)
        summary = json.loads(out)["summary"]
        self.assertEqual(summary["planned"], 1)
        self.assertEqual(summary["invalid"], 1)
        self.assertEqual(summary["elapsed_ms"], 0)

    def test_dry_run_flags_a_conflict_between_inputs(self):
        folder = self.work()
        write_image(folder / "rock_df_co.tga")
        write_image(folder / "rock_df_smdi.tga")
        code, out, _ = self.cli("--json", "--dry-run", "smdi", "--no-paa", folder)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["summary"]["planned"], 1)
        self.assertEqual(payload["summary"]["planned_skip"], 1)
        skipped = [item for item in payload["results"] if item["status"] == "planned-skip"][0]
        self.assertIn("would overwrite another input file", skipped["error"])

    def test_dry_run_marks_a_variant_file_as_skipped(self):
        folder = self.work()
        write_rvmat(folder / "metal.rvmat")
        write_rvmat(folder / "metal_worn.rvmat")
        code, out, _ = self.cli("--json", "--dry-run", "rvmat", folder)
        self.assertEqual(code, 0)
        summary = json.loads(out)["summary"]
        self.assertEqual((summary["planned"], summary["planned_skip"]), (1, 1))

    def test_dry_run_makes_strict_a_no_op(self):
        folder = self.work()
        self.assertEqual(self.cli("--dry-run", "game", "--mode", "df-nrm", folder)[0], 0)
        self.assertEqual(self.cli("--dry-run", "--strict", "game", "--mode", "df-nrm", folder)[0], 0)


class ProcessingTests(CliTestCase):
    def test_game_writes_the_planned_files(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, _ = self.cli("--json", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["outputs"])
        for output in result["outputs"]:
            self.assertTrue(Path(output).exists(), output)

    def test_game_auto_dispatches_by_suffix(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, _ = self.cli("--json", "game", "--auto", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["processor"], "DF_NRM")

    def test_delete_source_is_off_by_default(self):
        folder = self.work()
        source = folder / "a_df_nrm.tga"
        write_image(source)
        code, _, _ = self.cli("game", "--mode", "df-nrm", source)
        self.assertEqual(code, 0)
        self.assertTrue(source.exists())

    def test_smdi_writes_a_specular_map(self):
        folder = self.work()
        write_image(folder / "rock_co.tga")
        code, out, _ = self.cli("--json", "smdi", "--no-paa", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertTrue(Path(result["outputs"][0]).exists())

    def test_rvmat_writes_the_three_variants(self):
        folder = self.work()
        write_rvmat(folder / "metal.rvmat")
        code, out, _ = self.cli("--json", "rvmat", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertEqual(len(result["outputs"]), 3)

    def test_rvmat_variants_flag_selects_a_subset(self):
        folder = self.work()
        write_rvmat(folder / "metal.rvmat")
        code, out, _ = self.cli("--json", "rvmat", "--variants", "worn", folder)
        self.assertEqual(code, 0)
        outputs = json.loads(out)["results"][0]["outputs"]
        self.assertEqual([Path(item).name for item in outputs], ["metal_worn.rvmat"])

    def test_pbr_writes_the_group_outputs(self):
        folder = self.work("pbr")
        for name in ("wall_basecolor.png", "wall_normal.png", "wall_roughness.png", "wall_ao.png"):
            write_image(folder / name)
        code, out, _ = self.cli("--json", "pbr", "--no-paa", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertTrue(result["outputs"])
        for output in result["outputs"]:
            self.assertTrue(Path(output).exists(), output)

    def test_watermark_embed_needs_content(self):
        folder = self.work()
        write_image(folder / "a.tga", size=64)
        code, _, err = self.cli("watermark", folder)
        self.assertEqual(code, 2)
        self.assertIn("--content is required", err)

    def test_watermark_embed_writes_a_watermarked_copy(self):
        folder = self.work()
        write_image(folder / "a.tga", size=64)
        code, out, _ = self.cli("--json", "watermark", "--content", "hi", folder)
        self.assertEqual(code, 0)
        result = json.loads(out)["results"][0]
        self.assertEqual(result["status"], "success")
        self.assertEqual(Path(result["outputs"][0]).name, "a_watermarked.tga")

    def test_watermark_detect_needs_a_length(self):
        folder = self.work()
        write_image(folder / "a.tga", size=64)
        code, _, err = self.cli("watermark", "--mode", "detect", "--length", "0", folder)
        self.assertEqual(code, 2)
        self.assertIn("--length must be greater than 0", err)

    def test_smdi_paa_without_the_tool_fails_at_startup(self):
        folder = self.work()
        write_image(folder / "rock_co.tga")
        self.settings.write_text(json.dumps({"image_to_paa": str(self.root / "missing.exe")}), encoding="utf-8")
        code, _, err = self.cli("smdi", folder)
        self.assertEqual(code, 2)
        self.assertIn("ImageToPAA.exe is required", err)

    def test_a_missing_path_next_to_a_real_one_is_reported(self):
        folder = self.work()
        write_image(folder / "wall_basecolor.png")
        code, out, _ = self.cli("--json", "pbr", "--no-paa", folder, "Z:/does/not/matter/wall_normal.png")
        self.assertEqual(code, 1)
        payload = json.loads(out)
        self.assertEqual(payload["results"][-1]["status"], "failed")
        self.assertIn("path not found", payload["results"][-1]["error"])


class OutputContractTests(CliTestCase):
    def test_json_mode_emits_exactly_one_object(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, _ = self.cli("--json", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual(payload["command"], "game")
        self.assertIn("results", payload)
        self.assertIn("summary", payload)

    def test_json_mode_stays_clean_even_when_a_library_prints_a_banner(self):
        # blind-watermark 第一次用会往 stdout 打横幅，必须被挤到 stderr。
        folder = self.work()
        write_image(folder / "a.tga", size=64)
        code, out, err = self.cli("--json", "watermark", "--content", "hi", folder)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["results"][0]["status"], "success")
        self.assertIn("blind-watermark", err)

    def test_json_mode_keeps_progress_off_stdout(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, err = self.cli("--json", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        json.loads(out)
        self.assertNotIn("[1/1]", out)
        self.assertNotIn("[1/1]", err)

    def test_quiet_suppresses_progress(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, _, err = self.cli("--quiet", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        self.assertEqual(err.strip(), "")

    def test_verbose_keeps_progress_with_json(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, err = self.cli("--json", "--verbose", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        json.loads(out)
        self.assertIn("[1/1]", err)

    def test_text_mode_prints_one_line_per_input_plus_a_summary(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        code, out, _ = self.cli("game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        lines = [line for line in out.splitlines() if line.strip()]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("[OK]"))
        self.assertIn("succeeded=1", lines[1])

    def test_json_output_is_pure_ascii(self):
        folder = self.work("贴图")
        write_image(folder / "a_df_nrm.tga")
        code, out, _ = self.cli("--json", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        out.encode("ascii")
        self.assertEqual(json.loads(out)["summary"]["succeeded"], 1)


class SettingsCommandTests(CliTestCase):
    def test_path_prints_the_settings_file(self):
        code, out, _ = self.cli("settings", "path")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), str(self.settings))

    def test_list_json_is_a_single_object(self):
        code, out, _ = self.cli("--json", "settings", "list")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertIn("language", payload)
        self.assertIsInstance(payload["pbr_output_suffixes"], dict)

    def test_get_reads_a_dotted_key(self):
        code, out, _ = self.cli("--json", "settings", "get", "pbr_output_suffixes.co")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), "_co")

    def test_get_rejects_an_unknown_key(self):
        code, _, err = self.cli("settings", "get", "nope")
        self.assertEqual(code, 2)
        self.assertIn("unknown settings key", err)

    def test_set_writes_a_scalar(self):
        code, out, _ = self.cli("settings", "set", "smdi_specular_power", "7.5")
        self.assertEqual(code, 0)
        self.assertIn("smdi_specular_power = 7.5", out)
        self.assertEqual(json.loads(self.settings.read_text(encoding="utf-8"))["smdi_specular_power"], 7.5)

    def test_set_writes_one_nested_key(self):
        code, _, _ = self.cli("settings", "set", "pbr_output_suffixes.co", "_custom")
        self.assertEqual(code, 0)
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["pbr_output_suffixes"]["co"], "_custom")

    def test_set_rejects_a_wrong_type(self):
        code, _, err = self.cli("settings", "set", "smdi_specular_power", "abc")
        self.assertEqual(code, 2)
        self.assertIn("needs a number", err)
        self.assertFalse(self.settings.exists())

    def test_set_rejects_a_value_outside_the_enum(self):
        code, _, err = self.cli("settings", "set", "language", "klingon")
        self.assertEqual(code, 2)
        self.assertIn("must be one of", err)
        self.assertFalse(self.settings.exists())

    def test_set_rejects_an_unknown_key(self):
        code, _, err = self.cli("settings", "set", "nope", "1")
        self.assertEqual(code, 2)
        self.assertIn("unknown settings key", err)

    def test_set_refuses_to_overwrite_a_corrupted_file(self):
        self.settings.write_text("{oops", encoding="utf-8")
        code, _, err = self.cli("settings", "set", "language", "zh")
        self.assertEqual(code, 1)
        self.assertIn("cannot parse", err)
        self.assertEqual(self.settings.read_text(encoding="utf-8"), "{oops")

    def test_set_keeps_keys_it_does_not_touch(self):
        self.settings.write_text(json.dumps({"language": "zh", "theme": "light"}), encoding="utf-8")
        self.cli("settings", "set", "smdi_specular_power", "3")
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual((data["language"], data["theme"]), ("zh", "light"))

    def test_settings_commands_do_not_print_a_processing_summary(self):
        code, out, _ = self.cli("settings", "path")
        self.assertEqual(code, 0)
        self.assertNotIn("succeeded=", out)

    def test_settings_are_used_as_defaults(self):
        folder = self.work()
        write_image(folder / "a_df_nrm.tga")
        self.settings.write_text(json.dumps({"game_output_suffixes": {"DF_NRM": {"normal": "_CUSTOM"}}}), encoding="utf-8")
        code, out, _ = self.cli("--json", "--dry-run", "game", "--mode", "df-nrm", folder)
        self.assertEqual(code, 0)
        outputs = json.loads(out)["results"][0]["outputs"]
        self.assertTrue(any(item.endswith("_CUSTOM.png") for item in outputs), outputs)


class EntryPointTests(CliTestCase):
    def env(self) -> dict:
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC_ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        return env

    def test_the_module_entry_point_returns_the_exit_code(self):
        proc = subprocess.run([sys.executable, "-m", "dayz_texture_tool.cli"], capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env())
        self.assertEqual(proc.returncode, 2)
        self.assertIn("usage:", proc.stdout)

    def test_importing_the_cli_does_not_pull_in_qt(self):
        script = "import sys; import dayz_texture_tool.cli; print('PySide6' in sys.modules)"
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, encoding="utf-8", errors="replace", env=self.env())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "False")

    def test_the_console_script_is_declared(self):
        pyproject = (SRC_ROOT.parent / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('dayz-texture-tool-cli = "dayz_texture_tool.cli:main"', pyproject)


if __name__ == "__main__":
    unittest.main()
