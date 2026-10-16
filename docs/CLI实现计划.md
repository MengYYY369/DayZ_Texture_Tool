# DayZ 贴图工具 · CLI 实现计划

> 状态：**待实现**（v2，已按对抗性审查修订）。
> 目标读者：实现者（人或 AI）。读完后应能不看代码就开工，且不会与既有约定冲突。
> v1 → v2 修订点见文末「附录 A：审查修订记录」。

---

## 一、目标与定位

给项目加一个**无头命令行入口**，让 AI（或脚本）无需启动 GUI 即可驱动全部处理能力。

- **入口**：新增控制台脚本 `dayz-texture-tool-cli`，并支持 `python -m dayz_texture_tool.cli`。
- **实现方式**：直接调用现有处理层（`processors/`、`batch.py`、`models.py`、`settings.py`）。**这些层本来就不依赖 Qt，可以单独导入**（已实测：导入 `batch`、各 `processors`、`settings` 后 `PySide6 not in sys.modules`）。
- **不引入 Qt**：`cli.py` 绝不 `import PySide6`；只有 `gui` 子命令内部**延迟 import**。这样无显示器 / 未装 Qt 的环境也能跑。

一句话：**把 GUI 已有的五个操作，套一层稳定的命令行契约。**

---

## 二、明确不做的事

| 不做 | 原因 |
|---|---|
| 改任何图像处理算法 | 只加外壳。处理逻辑一行不动（**新增纯规划函数**是唯一例外，见第六节） |
| 改设置文件的格式与位置 | 仍是 `%APPDATA%\DayZ_Texture_Tool\settings.json`（即 `Path.home()/AppData/Roaming/DayZ_Texture_Tool`，`settings.py:8`），与 GUI 共享同一份真相 |
| 并行 / 多进程 | 对齐 GUI 的单工作线程，先做顺序执行；有需要再说 |
| `--output-dir` | 处理器都是"写在源文件旁边"，PBR2DayZ 的分组逻辑也依赖这一点，加输出目录会破坏它 |
| 常驻服务 / MCP / GUI 自动化 | 本轮只要 CLI。AI 用 `subprocess` 调用即可 |
| 给发布包塞 CLI 入口 | 本轮先保证源码可跑（`.venv` 里能用）；PyInstaller 是否额外出 CLI exe，留待后续单独决定 |
| 命令中途取消 | 与 GUI 一致：一批开始就得跑完 |

---

## 三、设计决策（冻结）

| # | 决策 | 结论 |
|---|---|---|
| Q1 | 定位 | 无头 CLI，直接调处理层 |
| Q2 | 覆盖面 | `game` `pbr` `watermark` `smdi` `rvmat` `settings` `gui` 七个子命令 |
| Q3 | 框架/入口 | `argparse`（标准库）；新增 `dayz-texture-tool-cli`；兼容 `-m dayz_texture_tool.cli` |
| Q4 | 输出契约 | 默认文本 + `--json`；退出码 0/1/2；结果走 stdout、进度走 stderr |
| Q5 | 设置集成 | 读 `settings.json` 作默认，flag 覆盖；`--settings PATH`；`settings` 子命令读写 |
| Q6 | 干跑 | `--dry-run` 只规划不落盘 |
| Q7 | 参数对等 | 与 GUI 对等，默认值全部对齐 GUI（即：flag 默认 `None` 时回落到 settings 里的对应值） |
| Q8 | 形态 | 位置参数 `paths...`（文件与目录混用） |
| Q9 | Game2PBR 模式 | 默认 `--mode` 显式；`--auto` 走后缀自动分发；模式名接受内部名与 `df-nrm` 风格，大小写不敏感 |
| Q10 | 文件夹展开 | **所有子命令统一递归展开目录**，按各自扩展名过滤（**偏离 GUI**：GUI 里 SMDI/水印不展开） |
| Q11 | PBR 隐藏参数 | 开放 `co_mode`/`specular`/`glossiness` 为可选 flag，默认等于处理器默认 |
| Q12 | 删除源文件 | **CLI 默认不删**，`--delete-source` 显式开启（**偏离 GUI**：GUI 里 Game/PBR 默认开） |
| Q13 | `settings` 粒度 | `path` / `list` / `get KEY` / `set KEY VALUE`，点号键，值按 JSON 解析，写入前**自校验**（见 N4） |
| Q14 | 运行时行为 | 进度→stderr；`--quiet` 关进度；`--json` 默认关进度；`--strict` 让"零成功"也返回 1 |
| Q15 | 测试与文档 | 补 `tests/test_cli.py`；中英文 README 各加一节 |
| Q16 | 输出位置 | 就地写、同名覆盖，无 `--output-dir` |
| Q17 | 架构约束 | `cli.py` 不 import Qt；`gui` 延迟导入；无子命令时打印帮助并退出码 2 |
| Q18 | 边界 | 路径不存在计入失败；零可处理文件不算失败（除非 `--strict`）；单进程顺序 |
| Q19 | Game 显式模式 | **显式 `--mode` 不套后缀过滤**；后缀分发只由 `--auto` 负责（**偏离 GUI**） |
| N1 | `--auto` 后缀表 | 用 **`settings.game_suffixes`**（回落 `DEFAULT_GAME_SUFFIXES`），可分发全部九个模式；输出后缀表用 `settings.game_output_suffixes` |
| N2 | `--out-suffix` 与 `--auto` | `--out-suffix` **仅对显式 `--mode` 有效**；与 `--auto` 同用 → 用法错误（退出码 2） |
| N3 | dry-run 状态词汇 | JSON 顶层加 `"dry_run": true`；状态用 `planned`/`planned-skip`/`invalid`；`--strict` 在 dry-run 下不生效 |
| N4 | `settings set` 校验 | CLI 自做**类型 + 枚举校验**（非法值退出码 2）；写入前检测配置文件是否损坏，损坏则报错、**不覆盖** |
| N5 | `smdi`/`watermark` 的 PAA | `--paa`（默认 on）在 `ImageToPAA.exe` 缺失/无效时**启动即预检失败**（退出码 2），不让每个文件硬失败 |

**三处有意偏离 GUI**（Q10/Q12/Q19）：统一文件夹展开、删除默认关、显式模式不套过滤。代码注释与 README 均须标注。

---

## 四、CLI 规格

```
dayz-texture-tool-cli [全局选项] <子命令> <paths...> [子命令选项]
```

### 全局选项

| 选项 | 说明 |
|---|---|
| `--settings PATH` | 用指定配置文件代替默认的 `settings.json` |
| `--json` | stdout 输出机器可读 JSON |
| `--quiet` | 不打印进度（stderr） |
| `--verbose` | `--json` 时也打印进度 |
| `--dry-run` | 只规划、不写盘 |
| `--strict` | "零个成功"也返回退出码 1（dry-run 下无效） |

### 子命令

> 约定：**默认值标注为「settings」的选项，其 flag 默认取 `None`，运行期回落到 `settings.json` 对应字段；显式传入才覆盖**（Q5/Q7）。括号内给出回落来源与 GUI 默认。

| 子命令 | 选项 |
|---|---|
| `game` | `--mode NAME`（内部名或 `df-nrm` 风格）**或** `--auto`（互斥、必填）；`--match {exact,fuzzy}`（**仅 `--auto`**，默认 settings.game_match_mode=exact）；`--delete-source`；`--out-suffix KEY=VALUE`（可重复，**仅显式 `--mode`**） |
| `pbr` | `--normal {directx,opengl}`=directx；`--resolution {auto,256,512,1024,2048}`=auto；`--prefix-mode {auto,current_folder,parent_folder,filename_prefix,custom}`（默认 settings.pbr_prefix_mode=auto）；`--custom-prefix STR`（默认 settings.pbr_custom_prefix）；`--match {exact,fuzzy}`（默认 settings.pbr_match_mode=fuzzy）；`--co-mode STR`=basecolor；`--specular F`=0.75；`--glossiness F`=1.0；`--paa/--no-paa`（默认 on）；`--watermark/--no-watermark`（默认 off）+ `--watermark-content`/`--watermark-password`（默认 settings）；`--delete-source`（默认 off） |
| `watermark` | `--mode {embed,detect}`=embed；`--content STR`（embed，默认 settings.watermark_content）；`--password STR`（默认 settings.watermark_password）；`--length INT`（detect，默认 settings.watermark_length）；`--overwrite`（embed，默认 off） |
| `smdi` | `--specular F`（默认 settings.smdi_specular_power=10）；`--paa/--no-paa`（默认 on） |
| `rvmat` | `--variants worn,damage,destruct`（默认三个全开）；`--damage-texture NAME=PATH`（可重复，覆盖 settings.rvmat_damage_textures） |
| `settings` | `path` / `list` / `get KEY` / `set KEY VALUE` |
| `gui` | 启动现有界面（等价于旧入口） |

**各选项的落地规则（必须实现）**

- `--normal`/`--resolution`：GUI 是硬编码默认（无 settings 字段），故 CLI 也硬编码，不回落到 settings。
- `--paa` 默认 on：**PBR 分支**缺 `ImageToPAA.exe` 时优雅跳过（`convert_pbr_group` 会给消息）；**SMDI / watermark 分支**缺工具时是硬失败，故 CLI 在进入处理前**预检**（N5），工具缺失/无效 → `parser.error`（退出码 2）。
- `game` 的 `--mode`/`--auto` 用 `mutually_exclusive_group(required=True)`；`--match` 只在 `--auto` 合法，非 auto 时给了 `--match` → `parser.error`（退出码 2）。
- 模式名归一化：`df-nrm` → 大写、`-` 换 `_` → `DF_NRM`。**注意**：`GAME2PBR_PROCESSORS` 含大小写不同的别名 `DirectInvertProcessor` 与 `DirectinvertProcessor`（都指向 `direct_invert`），归一化前先做精确匹配、再做大小写不敏感匹配，避免歧义；无法唯一确定时列候选并报错。
- `rvmat --variants`：接受语义名 `worn,damage,destruct`，映射为后缀元组 `('_worn','_damage','_destruct')`；非法名 → `parser.error`。`excluded_suffixes` 取 `settings.rvmat_excluded_suffixes`。
- `--out-suffix KEY=VALUE`：显式 `--mode` 下组装成 `dict[str,str]` 传给 `process_game2pbr_files`；键非法 → `parser.error`。

### 示例

```bash
dayz-texture-tool-cli game ./dump --mode df-nrm --dry-run --json
dayz-texture-tool-cli game ./dump --auto --match fuzzy
dayz-texture-tool-cli pbr ./tex --resolution 1024 --paa --json
dayz-texture-tool-cli watermark ./a.png --mode embed --content "id-42"
dayz-texture-tool-cli watermark ./a.png --mode detect --length 32
dayz-texture-tool-cli smdi ./co --specular 12
dayz-texture-tool-cli rvmat ./mats --variants worn,damage
dayz-texture-tool-cli settings path
dayz-texture-tool-cli settings get pbr_output_suffixes.co
dayz-texture-tool-cli settings set image_to_paa "D:\\steam\\...\\ImageToPAA.exe"
```

---

## 五、输出契约

### 退出码

| 码 | 含义 |
|---|---|
| `0` | 全部成功（含"跳过"）；`--strict` 下要求至少 1 个成功 |
| `1` | 存在失败项（`ProcessingResult.error` 非空），或**全部输入路径无效**（见下） |
| `2` | 用法错误（未知子命令、缺必填、`--mode`/`--auto` 冲突、`--match` 非 auto、`--out-suffix` 配 `--auto`、PAA 预检失败、非法 `--variants`/`--out-suffix`/`settings set` 值等） |

### 输入路径的处理（关键，v1 遗漏）

所有处理函数对**不存在的路径静默返回空**（`batch.collect_image_files` 对不存在路径返回 `[]`，`scan_pbr_paths` 过滤非文件）。因此 `expand_paths` 必须：

1. 逐个输入判断：不存在 → **合成一条 `ProcessingResult(success=False, error="path not found: ...", input_path=<原样>)`**，计入 `failed`。
2. 目录 → `rglob` 后按该子命令的扩展名表过滤、排序。
3. 显式文件 → 保留（不因扩展名不符而丢弃）；扩展名不符由处理器报"unsupported extension"并计入 `failed`。

由此：**全部输入路径无效 → 至少 1 条 failed → 退出码 1**（满足 Q18）；**目录存在但无匹配文件 → 空 BatchResult → 退出码 0**（除非 `--strict`）。二者边界由第 1 步区分。

### 文本模式（默认）

- stdout：每个输入一行 `[OK|FAIL|SKIP] <输入> -> <产出或原因>`，末尾一行汇总 `total/succeeded/failed/skipped · elapsed`。
- stderr：进度行（`--quiet` 关闭）。

### JSON 模式（`--json`）

stdout 只输出**一个** JSON 对象（进度默认关闭，`--verbose` 时进度仍写 stderr）：

```json
{
  "command": "game",
  "dry_run": false,
  "settings_path": "C:\\Users\\...\\settings.json",
  "results": [
    {
      "input": "C:\\dump\\a_nrm.tga",
      "status": "success",
      "processor": "DF_NRM",
      "outputs": ["C:\\dump\\a_Metal.png", "C:\\dump\\a_Rou.png", "C:\\dump\\a_N.png"],
      "error": "",
      "messages": ["DF_NRM: a_nrm.tga"],
      "elapsed_ms": 123,
      "metadata": {}
    }
  ],
  "summary": {"total": 1, "succeeded": 1, "failed": 0, "skipped": 0, "elapsed_ms": 130}
}
```

**`status` 取值**

| 模式 | 取值 | 派生规则 |
|---|---|---|
| 正常运行 | `success` / `skipped` / `failed` | `success=True`→success；`success=False` 且 `error` 空→skipped；`error` 非空→failed |
| `--dry-run` | `planned` / `planned-skip` / `invalid` | 会产出→planned；会跳过（生成物后缀、已是变体、无可转换贴图等）→planned-skip；路径不存在/扩展名不支持→invalid |

dry-run 时：`summary` 改为统计 `planned`/`planned-skip`/`invalid`；`elapsed_ms` 无意义，统一填 `0`；`outputs` 为**将产出**的路径；`--strict` 不生效（文档与 `--help` 均注明）。

**两条为了守住「stdout 只有一个 JSON」而加的实现约束（实现时发现，v2 原文没写）：**

1. JSON 一律用 `ensure_ascii=True` 序列化。中文路径会变成 `\uXXXX` 转义，代价是 JSON 里读不到中文，换来的是任何控制台代码页下都不会乱码、不会把 JSON 截断。
2. 跑处理类子命令期间，把 `sys.stdout` 临时重定向到 stderr，只留结果那一份 JSON 回 stdout。原因：`blind-watermark` 首次使用会往 stdout 打一段版权横幅，直接破坏 JSON 契约。`settings` 子命令不套这层包装（它不碰第三方库）。

`settings` 子命令的 stdout **不是**上面这个信封：`get` 直接输出该键的值本身，`list` 输出整个配置对象，`path` 输出一行路径。

---

## 六、模块与代码结构

新增单文件 `src/dayz_texture_tool/cli.py`（约 500–600 行）。若过长可拆 `cli/` 包，初版单文件即可。

### 6.1 复用的处理层函数（逐条核对过签名）

| 子命令 | 调用的处理层函数（签名以实际代码为准） |
|---|---|
| `game --mode` | `batch.process_game2pbr_files(files, processor, delete_source=False, output_suffixes=None, progress_callback=None)` |
| `game --auto` | `batch.process_game2pbr_auto(path, suffix_map=None, match_mode='exact', delete_source=False, output_suffix_map=None, progress_callback=None)` —— **单路径**，见 6.2 |
| `pbr` | `pbr2dayz.convert_pbr_files(files, root_context=None, ...)`（**先用目录展开成文件**，见 6.2；`convert_pbr_folder` 只收单目录，不用） |
| `watermark embed` | `watermark.add_watermark_files(files, content, password=1, progress_callback=None, image_to_paa=None, overwrite=False)` |
| `watermark detect` | `watermark.detect_watermark_files(files, password=1, watermark_length=0, progress_callback=None, image_to_paa=None)` |
| `smdi` | `smdi.convert_color_to_smdi_files(files, specular_power=10.0, make_paa=False, image_to_paa=None, progress_callback=None)` |
| `rvmat` | `rvmat.convert_rvmat_files(files, variants=('_worn','_damage','_destruct'), damage_textures=None, excluded_suffixes=..., progress_callback=None)` |
| `settings` | `settings.load_settings` / `settings.save_settings` |
| `gui` | 延迟 `from dayz_texture_tool.app import main` |

**注意**：`game`/`pbr`/`watermark` 的批量函数**不做冲突检测**（只有 `smdi`、`rvmat` 的批量函数做）。CLI 在 `--dry-run` 与正常跑之前，用 6.3 的规划逻辑做一次**冲突预检**，把"输出会覆盖另一输入/已被他人产出"的项提前标记（正常跑时合成失败项，dry-run 时标 `planned-skip`）。

### 6.2 需要自己写的薄工具

- `expand_paths(paths, extensions)`：见第五节（含为不存在路径合成失败项、跨盘处理）。
- `merge_batches(batches) -> BatchResult`：`BatchResult` 只有 `add()`，需自行聚合 `results` 与 `messages`；`game --auto`、以及 pbr 分 root 处理时要用。
- `emit_progress`：写 stderr，`--quiet`/`--json` 控制。
- `result_to_dict` / `batch_to_dict(batch, command, dry_run)`：`Path`→`str`。
- `compute_exit_code(batch, strict, dry_run)`。
- `preflight_paa(image_to_paa, need_paa)`：N5 的 PAA 预检。

### 6.3 规划函数（dry-run 与冲突预检）

**这是 v1 最大的漏洞：** `game`/`pbr`/`watermark` 没有可复用的公开规划函数，`smdi._planned_outputs` 在 `--paa` 时会**多报**一张中间 `.tga`（实际只留 `.paa`）。因此：

- **新增纯规划函数**（additive，不改现有行为，各自补单测），放在对应处理器模块里：
  - `game2pbr.plan_outputs(processor, path, output_suffixes) -> list[Path]`：复用 `_output`/`_suffixes` 规则，含 `direct_convert` 的"输出==输入则追加 `_converted`"特例；`merge_rgba` 需先判断同名 `_a` 图是否存在（不存在则该输入注定失败）。
  - `pbr2dayz.plan_group_outputs(group, output_suffixes) -> list[Path]`：把 `convert_pbr_group` 里内联的输出路径计算提取出来，供 `convert_pbr_group` 与规划共用（**重构内联为调用，行为不变**）。
  - `smdi.plan_outputs(path, make_paa) -> list[Path]`：返回**最终**产物（`make_paa=True` 时**只返回 `.paa`**），修正现 `_planned_outputs` 的多报；`_planned_outputs` 可改为调用它或删除。
  - `watermark.plan_output(path, overwrite) -> Path`：公开 `_output_path` 的默认命名 `{stem}_watermarked{suffix}`。
  - `rvmat` 已有公开的 `variant_output_path`，直接用。
- 冲突预检复用这些规划函数，不再复刻规则。
- `--dry-run` 的规划也全部走这些函数。

> 这是对 §二"处理逻辑一行不动"的**唯一例外**：只**新增/提取**纯函数，不改变任何既有处理路径的输入输出。实现后跑全量测试确认无回归。

### 6.4 参数解析（argparse）

- `build_parser()`：根 parser `add_subparsers(dest="command", required=False)`。
- **全局选项必须 `default=argparse.SUPPRESS`**，否则 `cli --json game ...` 中根解析出的 `True` 会被子 parser 的默认值覆盖（已实测复现）。所有读取一律 `getattr(args, name, default)`。
- 共享的全局 parser 片段用 `parents=[global_parser]`，且 `global_parser` 必须 `add_help=False`（否则 `-h` 冲突）。
- `--paa/--no-paa` 用 `argparse.BooleanOptionalAction`（Python ≥3.10，满足 `requires-python`）。
- 手动校验项（argparse 无法表达，用 `parser.error`）：`--mode`/`--auto` 互斥、`--match` 仅 `--auto`、`--out-suffix` 仅显式模式、PAA 预检、`--variants`/`--out-suffix` 值合法性、`settings set` 值合法性。
- `gui` 子命令忽略 `--json/--dry-run/--quiet`（文档注明无意义）。

### 6.5 `settings` 子命令

- `settings path`：打印解析后的配置文件路径。
- `settings list`：打印全部键值（`--json` 时输出 JSON）。
- `settings get KEY`：点号键读取；未知键 → 退出码 2。
- `settings set KEY VALUE`：
  - 值按 JSON 解析；Windows 路径建议用双反斜杠或正斜杠（README 给示例）。
  - **类型 + 枚举校验**（N4）：用 dataclass 字段类型（`get_type_hints`）校验标量；对枚举型字段（`pbr_prefix_mode`、`game_match_mode`、`pbr_match_mode`、`theme`、`language` 等）用白名单校验；非法 → 退出码 2，不写盘。
  - **损坏检测**：`load_settings` 会吞异常返回默认值（`settings.py:101`），直接 `set` 会用默认值**覆盖用户配置**。故 `set` 前先独立读取原文件，`json.loads` 失败 → 报错（退出码 1），**不覆盖**。
  - 嵌套 dict（如 `rvmat_damage_textures.destruct`）：点号键的最后一段作为 dict 内键，只改该键、保留其余。
- `save_settings(settings, path)` 落盘。

### 6.6 入口与打包

```toml
[project.scripts]
dayz-texture-tool = "dayz_texture_tool.app:main"          # 保持不变
dayz-texture-tool-cli = "dayz_texture_tool.cli:main"      # 新增
```

- `cli.py` 末尾：`if __name__ == "__main__": sys.exit(main())`（**必须带 `sys.exit`**，否则 `python -m dayz_texture_tool.cli` 退出码全变 0；`console_scripts` 的 wrapper 会自动 `sys.exit`，`-m` 不会）。
- `main() -> int` 返回退出码。
- `python -m dayz_texture_tool`（不带 `.cli`）仍走 `__main__.py` 启动 GUI，不变。

---

## 七、实现步骤（按依赖顺序，每步可独立验证）

1. **规划函数**：在 `game2pbr`/`pbr2dayz`/`smdi`/`watermark` 增加 6.3 的纯规划函数，跑全量测试确认无回归。
2. **骨架**：`cli.py` 建 `build_parser()`、`main()`，仅全局选项 + 帮助 + 无子命令退出码 2。验证 `python -m dayz_texture_tool.cli --help`。
3. **公共工具**：`expand_paths`（含合成失败项、跨盘 `ValueError` 捕获）、`merge_batches`、进度、`result_to_dict`、退出码。加单测。
4. **`game`**：显式 `--mode` 与 `--auto`（循环合并 BatchResult）两条路径 + `--dry-run` + 冲突预检。加单测。
5. **`pbr`**：目录展开成文件 → `convert_pbr_files`；全参数映射 + `--dry-run`。加单测。
6. **`watermark`**：embed/detect；`--dry-run` 用 `plan_output`。加单测。
7. **`smdi`**：`--specular` / `--paa` + PAA 预检；`--dry-run` 用修正后的 `plan_outputs`。加单测。
8. **`rvmat`**：`--variants` 映射 + `--damage-texture`。加单测。
9. **`settings`**：`path/list/get/set` + 类型/枚举校验 + 损坏检测。加单测。
10. **`gui`**：延迟导入。
11. **`pyproject.toml`** 脚本入口；`pip install -e .` 后验证 `dayz-texture-tool-cli`。
12. **测试**：补齐 `tests/test_cli.py`（第八节），跑全量 `python -m unittest discover -s tests`。
13. **文档**：README（英文）与 `README.zh-CN.md`（中文）各加「命令行」一节。

---

## 八、测试计划

新增 `tests/test_cli.py`，沿用现有 unittest 风格。**注意**：现有测试无 `conftest.py`，`test_batch_settings.py` 靠 `sys.path.insert(0,'src')`，`test_ui_pages.py` 在模块顶层 import PySide6 并设 `QT_QPA_PLATFORM=offscreen`；`test_cli.py` 需自做 `sys.path.insert`，且不假设同进程 `sys.modules` 干净。

覆盖点：

- 参数解析：`--mode`/`--auto` 互斥、未知子命令、缺 paths、`--match` 非 auto、`--out-suffix` 配 `--auto` → 退出码 2。
- 全局选项位置：`cli --json game ...` 与 `cli game ... --json` **两种位置都生效**（回归 6.4 的 SUPPRESS 修复）。
- `game --mode`：正常转换、`--out-suffix` 生效、显式模式**不套**后缀过滤（Q19）。
- `game --auto`：多路径循环合并、按后缀分发、生成物后缀被跳过（N1 用 settings 表）。
- `--dry-run`：不产生任何文件；`outputs` 为计划路径；状态用 `planned/planned-skip/invalid`；**对同一输入比对计划与实际产出**（须在 SMDI `--paa` 上通过，验证 6.3 的修正）。
- `--json`：stdout 整体可 `json.loads`；字段齐全；`status` 三态（正常）与三态（dry-run）分别正确。
- 退出码：成功 0 / 含失败 1 / 用法错误 2 / `--strict` 零成功 1 / dry-run 下 `--strict` 无效。
- 路径边界：不存在的路径 → 合成失败项、退出码 1；目录存在但无匹配文件 → 0。
- 目录展开：SMDI/水印喂目录能递归处理（Q10 偏离点）。
- `settings get/set`：点号键读、嵌套 dict 单键写、非法值/未知键退出码 2、损坏文件不覆盖（退出码 1）。
- 不加载 Qt：用**子进程** `python -c "import dayz_texture_tool.cli, sys; assert 'PySide6' not in sys.modules"`（不能靠"跑完 CLI 再查"——进程已退出）。
- PAA：`--paa` 在 `image_to_paa` 缺失时，`pbr` 优雅跳过、`smdi`/`watermark` 预检失败（退出码 2）。需 mock 或跳过，避免依赖真实 `ImageToPAA.exe`。

---

## 九、风险与边界

| 风险 | 处理 |
|---|---|
| dry-run 计划与真实产出不一致 | 新增纯规划函数（6.3）并让处理路径也调用它们，消除"两套规则"；测试对同一输入比对计划与实际 |
| 规划函数引入回归 | 只新增/提取、不改行为；每加一个跑全量测试；作为 §二 的唯一例外显式记录 |
| 全局选项在子命令前后位置不一致 | `default=argparse.SUPPRESS` + `getattr`；单测覆盖两种位置 |
| `--json` 混入进度污染 stdout | 进度只写 stderr；`--json` 默认关进度；单测断言 stdout 可整体 `json.loads` |
| 跨盘路径让 pbr 崩 | `expand_paths`/pbr 分支捕获 `root_context_for_files` 的 `ValueError`，转失败项或 `parser.error` |
| `settings set` 静默覆盖损坏配置 | 写前独立 `json.loads` 检测，损坏则退出码 1、不写 |
| Windows 专有依赖（PAA/回收站） | PAA 用 N5 预检；回收站仅在 `--delete-source` 时用到（`ctypes.windll`，Windows-only，非 Windows 下 `--delete-source` 明确报错） |
| 发布包不含 CLI | 本轮明确不做；如需，后续在 `DayZ_Texture_Tool.spec` 增加 console 入口 |

---

## 十、验收标准

以下各项已于实现完成后逐条实测（2026-02，Windows + 项目 `.venv`）：

- [x] 七个子命令全部可用，`--help` 自解释。
- [x] `--json` 输出可被 `json.loads` 直接解析，字段符合第五节。
- [x] 退出码符合第五节的 0/1/2 约定；全局选项两种位置都生效。
- [x] `--dry-run` 不落盘，且计划路径与实际产出一致（含 SMDI `--paa`；六条流水线逐条对比过 `planned == real`）。
- [x] 不存在的路径计入失败并返回 1；目录无匹配文件返回 0。
- [x] `cli.py` 不 import Qt（`gui` 除外），子进程断言通过（`sys.modules` 里无 `PySide*`/`Qt*`）。
- [x] 三处有意偏离 GUI 的行为在代码注释（`cli.py` 模块 docstring）与 README 中均有说明。
- [x] `python -m unittest discover -s tests` 全绿：217 用例（原有 155 + 新增 62）。
- [x] 中英文 README 均含 CLI 用法。
- [x] `dayz-texture-tool-cli` 与 `python -m dayz_texture_tool.cli` 两条入口都能跑，退出码正确传出。

---

## 附录 A：审查修订记录（v1 → v2）

对抗性审查发现、并已在本版修正的问题：

1. `process_game2pbr_auto` 是**单路径**，v1 误当批量入口 → 改为"循环 + `merge_batches`"（6.1/6.2）。
2. `--dry-run`"复用纯函数"不成立（game/pbr 无公开规划函数、smdi 多报 `.tga`、watermark 缺规划）→ 新增纯规划函数（6.3）。
3. PAA 缺失行为分处理器不同（PBR 跳过、SMDI/watermark 硬失败）→ 加 N5 预检（4/6.2）。
4. `settings set`"经 AppSettings 校验"不成立 → 改自校验 + 损坏检测（N4/6.5）。
5. 默认值硬编码违反 Q5/Q7 → 全部 `default=None` 回落 settings（四）。
6. argparse `parents` 会覆盖全局选项 → `default=SUPPRESS` + `getattr` + `add_help=False`（6.4）。
7. "路径不存在计入失败"无落地机制 → `expand_paths` 合成失败项（五）。
8. dry-run 的 `status` 自相矛盾 → 独立状态词汇 `planned/planned-skip/invalid`（N3/五）。
9. `-m` 入口漏 `sys.exit` → 修正（6.6）。
10. `rvmat --variants` 映射、`--auto` 后缀表来源（N1）、`--out-suffix` 形状（N2）、跨盘 `ValueError`、`settings.json` 路径注释——均已修正。
