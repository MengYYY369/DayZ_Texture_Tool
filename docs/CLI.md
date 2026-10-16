# Command line

Run all five processing pipelines without opening the window. Good for scripting a batch, and good for letting an AI agent drive the tool.

**English** · [中文](CLI.zh-CN.md)

> This document explains **how to use it**. For why it is built this way and how the code is organised, see [`CLI实现计划.md`](CLI实现计划.md) (in Chinese).

---

## 1. Two entry points

Once installed (`pip install -e .`) you get two commands:

```bash
# 1. Standalone command
dayz-texture-tool-cli game --auto "C:\dump\rock"

# 2. Module form, identical behaviour
python -m dayz_texture_tool.cli game --auto "C:\dump\rock"
```

The original `dayz-texture-tool` is unchanged — it still opens the GUI.

If you would rather not touch the system PATH, use the second form.

---

## 2. Up and running in three minutes

```bash
# See what would happen, without writing anything
python -m dayz_texture_tool.cli --dry-run game --auto "C:\dump\rock"

# Happy with it — drop --dry-run and run for real
python -m dayz_texture_tool.cli game --auto "C:\dump\rock"
```

Output looks like this:

```text
[OK] C:\dump\rock\rock_df_nrm.tga -> rock_df_nrm_Metal.png, rock_df_nrm_Rou.png, rock_df_nrm_N.png
total=1 · succeeded=1 · failed=0 · skipped=0 · elapsed_ms=11
```

For a program to read, add `--json`:

```bash
python -m dayz_texture_tool.cli --json game --auto "C:\dump\rock"
```

---

## 3. General rules

These apply to every processing subcommand.

### 3.1 How to pass paths

Every subcommand takes **one or more** paths, and files and folders can be mixed freely.

| What you pass | What happens |
| --- | --- |
| A folder | It is **walked all the way down**, so files in subfolders are processed too |
| A file you name explicitly | Taken as-is, even if the extension is unsupported (it will fail later) |
| A path that does not exist | Recorded as one failure on its own; exit code 1 |

### 3.2 Where files are written

**In place**, in the same folder as the source file. There is no `--output-dir` and no equivalent.

Files of the same name are **overwritten** without asking. So run `--dry-run` first the first time.

### 3.3 Where progress and results go

| Content | Stream |
| --- | --- |
| Results (per-item pass/fail) | **stdout** |
| Progress (`[1/10] xxx.tga`) | **stderr** |

They are split so that `--json` output is always clean and directly parseable. The JSON contains ASCII only, so it survives any console code page.

Pass `--quiet` to suppress progress. Conversely, to keep progress while using `--json`, pass `--verbose`.

### 3.4 Exit codes

| Code | When |
| --- | --- |
| `0` | Everything that needed doing was done |
| `1` | At least one input failed; or `--strict` was given and nothing succeeded |
| `2` | Bad usage: unknown subcommand, unknown mode name, incompatible flags, invalid setting value |

With no subcommand at all, the CLI prints help and returns 2.

### 3.5 Settings file supplies the defaults

Every flag defaults to the value in `settings.json` (default location: see `settings path` below). **Any flag you write on the command line always beats the file.**

So once the tool is configured in the GUI, the command line just works — nothing to repeat.

---

## 4. Global options

These may go **before or after** the subcommand.

| Option | Effect |
| --- | --- |
| `--json` | Emit one JSON block, for programs |
| `--dry-run` | Work out what would happen; write nothing |
| `--settings PATH` | Use that particular `settings.json` |
| `--quiet` | Do not print progress |
| `--verbose` | Keep progress even with `--json` |
| `--strict` | Return 1 if nothing succeeded; no effect with `--dry-run` |
| `-h`, `--help` | Help |

---

## 5. Subcommands

Seven in total: `game`, `pbr`, `watermark`, `smdi`, `rvmat`, `settings`, `gui`.

### 5.1 `game` — Game2PBR

One source texture in, one to four out.

```bash
python -m dayz_texture_tool.cli game (--mode NAME | --auto) [options] PATH [PATH ...]
```

You **must** pick one of the two: `--mode` names a processor explicitly, or `--auto` infers it from the filename suffix.

| Option | Meaning |
| --- | --- |
| `--mode NAME` | Processor name, see the table below. Case and hyphens are forgiving (`DF_NRM` = `df-nrm` = `df_nrm`) |
| `--auto` | Pick the processor from the filename suffix |
| `--match {exact,fuzzy}` | Only meaningful with `--auto`. Defaults to `game_match_mode` from settings (default `exact`) |
| `--out-suffix KEY=VALUE` | Override one output suffix. Repeatable. **Only valid with `--mode`** |
| `--delete-source` | Send the source to the recycle bin after processing. Off by default |

**The nine processors**

| Mode name | What it does | Output suffixes | Input suffix `--auto` recognises |
| --- | --- | --- | --- |
| `DF_NRM` | Delta Force NRM: alpha → metallic, blue → roughness, RG → normal | `_Metal` `_Rou` `_N` | `_nrm` |
| `DF_MRA` | Delta Force MRA: R → metallic, G → roughness, B → AO | `_met` `_rou` `_ao` | `_mra` |
| `ABI_ORN` | Arena Breakout Infinite ORN: G → roughness, R → AO, BA → normal | `_Rou` `_AO` `_N` | `_orn` |
| `SplitColorAlphaProcessor` | RGBA → opaque colour map + greyscale alpha map | `_rgb` `_alpha` | `_coloralpha` |
| `SplitRGBAProcessor` | RGBA → four independent greyscale channel maps | `_r` `_g` `_b` `_a` | `_rgba` |
| `MergeRGBAProcessor` | Colour map + sibling `_a` alpha map → RGBA | `_merged` | `_merge` |
| `XYNormalMapProcessor` | Rebuild a full normal from XY via `Nz = sqrt(1 - Nx² - Ny²)` | `_normal` | `_xy` |
| `DirectConvertProcessor` | Copy pixels unchanged, change format only | *(none)* | `_convert` |
| `DirectinvertProcessor` | Invert RGB (`1 - x`), with special handling for the blue channel | `_invert` | `_invert` |

The KEY in `--out-suffix` is a **slot** in the "Output suffixes" column above, not the suffix itself. `DF_NRM` has three slots, `metal` / `roughness` / `normal`:

```bash
# Rename the normal map from _N to _normal
python -m dayz_texture_tool.cli game --mode DF_NRM --out-suffix normal=_normal "C:\dump\rock"
```

A wrong slot name is an error, and the message lists the slots that mode does have.

**Examples**

```bash
# Infer the processor
python -m dayz_texture_tool.cli game --auto "C:\dump\rock"

# Name it explicitly
python -m dayz_texture_tool.cli game --mode DF_NRM "C:\dump\rock"

# Fuzzy matching (the suffix need not match exactly)
python -m dayz_texture_tool.cli game --auto --match fuzzy "C:\dump\rock"
```

### 5.2 `pbr` — PBR2DayZ

Groups textures by "folder + prefix" and packs each group into DayZ textures.

```bash
python -m dayz_texture_tool.cli pbr [options] PATH [PATH ...]
```

| Option | Meaning |
| --- | --- |
| `--normal {directx,opengl}` | Normal convention. Default `directx` |
| `--resolution {auto,256,512,1024,2048}` | Output resolution. Default `auto` |
| `--prefix-mode {...}` | Prefix rule: `auto` `current_folder` `parent_folder` `filename_prefix` `custom`. Default from settings |
| `--custom-prefix STR` | Prefix used by `--prefix-mode custom`. Default from settings |
| `--match {exact,fuzzy}` | How filenames are classified. Defaults to `pbr_match_mode` from settings (default `fuzzy`) |
| `--co-mode STR` | How CO is produced: `basecolor` (default, colour copied straight through) or `specular` (specular separation from the metallic map) |
| `--specular FLOAT` | SMDI specular power. Default `0.75` |
| `--glossiness FLOAT` | SMDI glossiness. Default `1.0` |
| `--paa` / `--no-paa` | Whether to convert to PAA. **On by default** |
| `--watermark` / `--no-watermark` | Also embed a watermark. Off by default |
| `--watermark-content STR` | Watermark text. Default from settings |
| `--watermark-password STR` | Watermark password. Default from settings |
| `--delete-source` | Send the source to the recycle bin after processing. Off by default |

**Input types** are recognised by keyword: colour, normal, roughness, metallic, AO. **Outputs**: `_co`, `_nohq`, `_smdi`, `_as`.

A group may hold one to five source images — **only the types actually present produce an output**.

```bash
python -m dayz_texture_tool.cli pbr --no-paa --watermark --watermark-content "my mod" "C:\dump\wall"
```

### 5.3 `watermark` — Watermark

Invisible blind watermarking via `blind-watermark`. Once embedded, the image looks completely unchanged to the eye; it can later be recovered given the password and the watermark length.

```bash
python -m dayz_texture_tool.cli watermark [options] PATH [PATH ...]
```

| Option | Meaning |
| --- | --- |
| `--mode {embed,detect}` | Embed or detect. Default `embed` |
| `--content STR` | Watermark text. **Required when embedding.** Default from settings |
| `--password STR` | Password. Default from settings |
| `--length N` | Watermark bit length. **Required when detecting** (must be greater than 0). Default from settings |
| `--overwrite` | Write back over the source. Off by default (otherwise saved as `xxx_watermarked.tga`) |

Embedding and detecting are two separate actions:

```bash
# Embed
python -m dayz_texture_tool.cli watermark --content "my mod" "C:\dump"

# Detect (use the length reported when embedding)
python -m dayz_texture_tool.cli watermark --mode detect --length 15 "C:\dump"
```

After embedding, the result carries a `watermark_length` — that is the length to pass next time you detect.

### 5.4 `smdi` — SMDI

One colour texture in, one specular map out.

```bash
python -m dayz_texture_tool.cli smdi [options] PATH [PATH ...]
```

| Option | Meaning |
| --- | --- |
| `--specular FLOAT` | Specular power. Default from settings (default `10.0`) |
| `--paa` / `--no-paa` | Emit `.paa` or `.tga`. **Defaults to PAA** |

```bash
python -m dayz_texture_tool.cli smdi --specular 12.5 "C:\dump\rock_co.tga"

# Without PAA
python -m dayz_texture_tool.cli smdi --no-paa "C:\dump\rock_co.tga"
```

### 5.5 `rvmat` — RVMAT

One material in, up to three wear variants out.

```bash
python -m dayz_texture_tool.cli rvmat [options] PATH [PATH ...]
```

| Option | Meaning |
| --- | --- |
| `--variants LIST` | Which ones, comma-separated, from `worn` `damage` `destruct`. All three by default |
| `--damage-texture NAME=PATH` | Replace one variant's Stage3 texture. Repeatable |

```bash
# Worn variant only
python -m dayz_texture_tool.cli rvmat --variants worn "C:\dump"

# Replace the worn variant's texture
python -m dayz_texture_tool.cli rvmat --damage-texture worn=dz\characters\data\worn_mc.paa "C:\dump"
```

### 5.6 `settings` — Read and write settings

```bash
python -m dayz_texture_tool.cli settings path            # where the settings file is
python -m dayz_texture_tool.cli settings list            # everything
python -m dayz_texture_tool.cli settings get KEY         # read one
python -m dayz_texture_tool.cli settings set KEY VALUE   # write one
```

KEY may drill down with dots:

```bash
python -m dayz_texture_tool.cli settings get pbr_output_suffixes.co      # _co
python -m dayz_texture_tool.cli settings set pbr_output_suffixes.co _custom
```

`set` first checks that the value matches the field's type and allowed values. If the existing file is not already valid JSON it **fails rather than writing** — it will never quietly replace your configuration with defaults.

Values are interpreted by field type: numbers as `12.5`, booleans as `true` / `false`, objects and arrays as JSON, strings as-is.

### 5.7 `gui` — Open the window

```bash
python -m dayz_texture_tool.cli gui
```

This is the only subcommand that loads the GUI toolkit. The others never touch Qt, so they work on a machine with no display.

---

## 6. How `--dry-run` works

It **writes no files at all** — it only reports what it would do.

In JSON the status vocabulary changes:

| Status | Meaning |
| --- | --- |
| `planned` | Would be processed; outputs listed in `outputs` |
| `planned-skip` | Would be skipped (suffix does not match, already a generated output, no convertible textures, …). The reason is in `messages` |
| `invalid` | Path does not exist, or unsupported extension |

`summary` follows suit, counting `planned` / `planned-skip` / `invalid`, and `elapsed_ms` is uniformly `0`.

`--strict` has no effect under `--dry-run`.

---

## 7. JSON output

With `--json`, stdout holds **exactly one** JSON object:

```json
{
  "command": "game",
  "dry_run": false,
  "settings_path": "C:\\Users\\you\\AppData\\Roaming\\DayZ_Texture_Tool\\settings.json",
  "results": [
    {
      "input": "C:\\dump\\rock\\rock_df_nrm.tga",
      "status": "success",
      "processor": "DF_NRM",
      "outputs": ["C:\\dump\\rock\\rock_df_nrm_Metal.png", "C:\\dump\\rock\\rock_df_nrm_Rou.png", "C:\\dump\\rock\\rock_df_nrm_N.png"],
      "error": "",
      "messages": ["DF_NRM: rock_df_nrm.tga"],
      "elapsed_ms": 123,
      "metadata": {}
    }
  ],
  "summary": {"total": 1, "succeeded": 1, "failed": 0, "skipped": 0, "elapsed_ms": 130}
}
```

On a real run `status` is one of `success` / `skipped` / `failed`; under `--dry-run` it becomes one of the three from section 6.

`metadata` may carry: `watermark_length` when embedding a watermark.

**The `settings` subcommand does not use this envelope** — it prints the value itself:

| Command | Output |
| --- | --- |
| `settings path` | One line, the path |
| `settings list` | The whole configuration object |
| `settings get KEY` | That key's value (JSON-encoded with `--json`, so strings are quoted) |
| `settings set KEY VALUE` | One confirmation line, `KEY = VALUE` |

---

## 8. Three differences from the GUI

These three are **deliberate**, not bugs.

1. **Folders are always walked down.** In the GUI only Game2PBR, PBR2DayZ and RVMAT do this; watermark and SMDI do not.
2. **`--delete-source` is off by default.** In the GUI it is on. An accidental delete on the command line is far more expensive, so it is reversed here.
3. **An explicit `--mode` does not filter by suffix.** The GUI hides rows that do not match the current processor; on the command line every file you name is processed. To have the processor inferred, use `--auto`.

---

## 9. Which keys the settings file holds

Run `settings list` for all of them. The common ones:

| Key | Type | Default | Which flag it feeds |
| --- | --- | --- | --- |
| `image_to_paa` | string | empty | Location of `ImageToPAA.exe` |
| `language` | string | `en` | Interface language |
| `theme` | string | `dark` | Interface theme, `dark` or `light` |
| `game_match_mode` | string | `exact` | `game --match` |
| `pbr_match_mode` | string | `fuzzy` | `pbr --match` |
| `pbr_prefix_mode` | string | `auto` | `pbr --prefix-mode` |
| `pbr_custom_prefix` | string | empty | `pbr --custom-prefix` |
| `watermark_content` | string | empty | `watermark --content` |
| `watermark_password` | string | `1` | `watermark --password` |
| `watermark_length` | int | `0` | `watermark --length` |
| `smdi_specular_power` | float | `10.0` | `smdi --specular` |
| `game_suffixes` | object | see `settings list` | What `game --auto` dispatches on |
| `game_output_suffixes` | object | see `settings list` | Per-mode output suffixes |
| `pbr_suffixes` | object | see `settings list` | PBR input-type keywords |
| `pbr_output_suffixes` | object | `co/nohq/smdi/as` | PBR output suffixes |
| `rvmat_damage_textures` | object | three `dz\characters\...` paths | Per-variant default textures |
| `rvmat_excluded_suffixes` | array | `_worn` `_damage` `_destruct` | Which files are not treated as sources |
| `last_page`, `window_geometry` | — | — | GUI state; irrelevant to the command line |

When writing object-valued keys such as `game_suffixes` / `game_output_suffixes` / `pbr_suffixes`, **what you write is merged into the defaults**, not replaced wholesale. So to change one entry, write just that entry.

---

## 10. About PAA

`ImageToPAA.exe` (bundled with DayZ Tools on Steam, free) is needed in several places:

- When `smdi --paa` or `pbr --paa` has to produce a PAA
- When a `.paa` is the input or the output (watermarking, SMDI on `.paa`)

**If it cannot be found the command fails outright (exit code 2); it never degrades silently.** That is intentional: better to tell you something is missing than to let you believe a PAA was produced when it was not.

To avoid PAA entirely, pass `--no-paa` (available on both `pbr` and `smdi`).

---

## 11. Common pitfalls

### 11.1 Running the same command twice on the same folder

After the first run, `rock_df_nrm_Metal.png` and friends sit right next to the source. Running the same command on the **same folder** again picks those outputs up as inputs, and you get:

```
[FAIL] ...\rock_df_nrm.tga -> Output rock_df_nrm_Metal.png would overwrite another input file in this batch.
```

Exit code 1. The current behaviour is to **report the error and write nothing** rather than plough ahead and overwrite.

To re-run, name the source file directly instead of passing the whole folder:

```bash
python -m dayz_texture_tool.cli game --mode DF_NRM "C:\dump\rock\rock_df_nrm.tga"
```

Or move the previous run's outputs out of the way first.

### 11.2 An explicit `--mode` processes the outputs too

Because of point 3 in section 8, `game --mode DF_NRM <folder>` processes **every** image in the folder as DF_NRM, including the `rock_df_nrm_Metal.png` from last time. The result is nonsense like `rock_df_nrm_Metal_Metal.png`.

When passing a folder, prefer `--auto` — it only processes files whose suffix matches an input mode.

### 11.3 Same name means overwritten

There is no "skip if exists" option; outputs simply overwrite. Run `--dry-run` first.

### 11.4 Paths spanning drives

`pbr` needs to group textures together, so it requires all inputs to be on the same drive. Across drives it fails with exit code 2.

---

## 12. Cheat sheet for scripts / AI

```bash
# Machine-readable results: add --json, read stdout, look at summary and results
python -m dayz_texture_tool.cli --json game --auto "C:\dump\rock"

# See what it would do without any risk: add --dry-run
python -m dayz_texture_tool.cli --json --dry-run game --auto "C:\dump\rock"

# Only care about success: use the exit code (0 ok / 1 failures / 2 bad usage)
python -m dayz_texture_tool.cli --quiet game --auto "C:\dump\rock" && echo OK

# Treat "nothing succeeded" as a failure too
python -m dayz_texture_tool.cli --strict --quiet game --auto "C:\dump\rock"

# Run against a throwaway config, leaving the user's settings alone
python -m dayz_texture_tool.cli --settings "C:\tmp\s.json" --json game --auto "C:\dump\rock"
```

A few points to keep in mind:

- Results go to **stdout**, progress to **stderr**; the two never mix.
- The JSON is ASCII only — a Chinese path appears as `\uXXXX` escapes — so any code page can read it.
- Every flag defaults to the value in `settings.json`; anything written on the command line wins.
- Global flags work before or after the subcommand.
- When unsure, `--dry-run` first.
- **Text output uses the console's encoding**, not UTF-8 (the `·` separators are not ASCII). If you are parsing output programmatically, use `--json` rather than scraping the text.
