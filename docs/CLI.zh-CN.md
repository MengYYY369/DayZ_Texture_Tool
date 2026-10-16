# 命令行用法

不打开窗口也能跑界面里的那五套处理流程。适合写成脚本批量处理，也适合让 AI 直接调用。

[English](CLI.md) · **中文**

> 这份文档讲**怎么用**。想了解为什么这样设计、代码怎么组织，看 [`CLI实现计划.md`](CLI实现计划.md)。

---

## 一、两条入口

装好之后（`pip install -e .`），有两个命令：

```bash
# 1. 独立命令
dayz-texture-tool-cli game --auto "C:\dump\rock"

# 2. 模块方式，效果完全一样
python -m dayz_texture_tool.cli game --auto "C:\dump\rock"
```

原来的 `dayz-texture-tool` 没变，仍然是打开图形界面。

如果不想动系统的 PATH，用第二条就行。

---

## 二、三分钟上手

```bash
# 看看会发生什么，不写任何文件
python -m dayz_texture_tool.cli --dry-run game --auto "C:\dump\rock"

# 确认没问题，去掉 --dry-run 真跑
python -m dayz_texture_tool.cli game --auto "C:\dump\rock"
```

输出长这样：

```
[OK] C:\dump\rock\rock_df_nrm.tga -> rock_df_nrm_Metal.png, rock_df_nrm_Rou.png, rock_df_nrm_N.png
total=1 · succeeded=1 · failed=0 · skipped=0 · elapsed_ms=9
```

想给程序读，加 `--json`：

```bash
python -m dayz_texture_tool.cli --json game --auto "C:\dump\rock"
```

---

## 三、通用规则

这几条对所有处理子命令都一样。

### 3.1 路径怎么给

每个子命令后面可以跟**一个或多个**路径，文件和文件夹混着给也行。

| 给的是什么 | 怎么处理 |
| --- | --- |
| 文件夹 | **一直往里翻**，子文件夹里的东西也会被处理 |
| 明确写出的文件 | 原样收下，哪怕扩展名不认识（不认识的后面会报错） |
| 不存在的路径 | 单独记为一条失败，退出码 1 |

### 3.2 文件写到哪

**就地写**，跟源文件同一个文件夹，没有 `--output-dir` 之类的选项。

同名文件会被**直接覆盖**，不问。所以第一次跑之前建议先 `--dry-run`。

### 3.3 进度和结果分别去哪

| 内容 | 去哪 |
| --- | --- |
| 处理结果（每条的成败） | **标准输出** |
| 进度（`[1/10] xxx.tga`） | **标准错误** |

分开是为了 `--json` 的输出永远是干净的、能被程序直接解析。JSON 只含 ASCII 字符，换什么控制台代码页都不会乱码。

不想看进度就加 `--quiet`；反过来，加了 `--json` 还想看进度，加 `--verbose`。

### 3.4 退出码

| 退出码 | 什么时候 |
| --- | --- |
| `0` | 该做的都做了 |
| `1` | 至少有一个输入失败；或者加了 `--strict` 而一件都没成功 |
| `2` | 用法错了：子命令不认识、模式名不认识、开关搭配不对、设置值不合法 |

没写子命令时打印帮助并返回 2。

### 3.5 设置文件当默认值

每个开关的默认值都取自 `settings.json`（默认位置见下面的 `settings path`）。**命令行上写了的开关永远优先于文件。**

所以在界面里配好之后，命令行直接就能用，不用重复填。

---

## 四、全局选项

放在子命令**前面或后面都行**。

| 选项 | 作用 |
| --- | --- |
| `--json` | 输出一整块 JSON，给程序读 |
| `--dry-run` | 只试算，不写任何文件 |
| `--settings PATH` | 用指定的那个 `settings.json` |
| `--quiet` | 不打印进度 |
| `--verbose` | 配 `--json` 时也保留进度 |
| `--strict` | 一件都没成功就返回 1；配 `--dry-run` 时无效 |
| `-h`, `--help` | 帮助 |

---

## 五、子命令

一共七个：`game`、`pbr`、`watermark`、`smdi`、`rvmat`、`settings`、`gui`。

### 5.1 `game` —— Game2PBR

一张源贴图进去，一到四张出来。

```bash
python -m dayz_texture_tool.cli game (--mode NAME | --auto) [选项] PATH [PATH ...]
```

**必须二选一**：要么 `--mode` 手动指定处理器，要么 `--auto` 让它自己从文件名后缀判断。

| 选项 | 说明 |
| --- | --- |
| `--mode NAME` | 处理器名字，见下表。大小写和连字符都能通融（`DF_NRM` = `df-nrm` = `df_nrm`） |
| `--auto` | 按文件名后缀自动挑处理器 |
| `--match {exact,fuzzy}` | 只在 `--auto` 时有效，默认取设置里的 `game_match_mode`（默认 `exact`） |
| `--out-suffix KEY=VALUE` | 改一个输出后缀，可重复，**只在 `--mode` 时有效** |
| `--delete-source` | 处理完把源文件丢进回收站，默认关 |

**九个处理器**

| 模式名 | 做什么 | 输出后缀 | `--auto` 认的输入后缀 |
| --- | --- | --- | --- |
| `DF_NRM` | 三角洲行动 NRM：透明通道→金属度，蓝通道→粗糙度，RG→法线 | `_Metal` `_Rou` `_N` | `_nrm` |
| `DF_MRA` | 三角洲行动 MRA：R→金属度，G→粗糙度，B→AO | `_met` `_rou` `_ao` | `_mra` |
| `ABI_ORN` | 暗区突围无限 ORN：G→粗糙度，R→AO，BA→法线 | `_Rou` `_AO` `_N` | `_orn` |
| `SplitColorAlphaProcessor` | RGBA 拆成不透明彩色图 + 灰度透明图 | `_rgb` `_alpha` | `_coloralpha` |
| `SplitRGBAProcessor` | RGBA 四通道各自拆成独立灰度图 | `_r` `_g` `_b` `_a` | `_rgba` |
| `MergeRGBAProcessor` | 彩色图 + 同名 `_a` 透明图合并成 RGBA | `_merged` | `_merge` |
| `XYNormalMapProcessor` | 按 `Nz = sqrt(1 - Nx² - Ny²)` 由 XY 重建完整法线 | `_normal` | `_xy` |
| `DirectConvertProcessor` | 原样复制像素，只改格式 | *（无后缀）* | `_convert` |
| `DirectinvertProcessor` | RGB 反相（`1 - x`），蓝通道另有特殊处理 | `_invert` | `_invert` |

`--out-suffix` 的 KEY 是上表「输出后缀」那一列的**位置**，不是后缀本身。比如 `DF_NRM` 有三个位置 `metal` / `roughness` / `normal`：

```bash
# 把法线那张从 _N 改成 _normal
python -m dayz_texture_tool.cli game --mode DF_NRM --out-suffix normal=_normal "C:\dump\rock"
```

位置名写错了会报错，并在错误信息里列出这个模式有哪些位置可用。

**例子**

```bash
# 自动判断
python -m dayz_texture_tool.cli game --auto "C:\dump\rock"

# 手动指定
python -m dayz_texture_tool.cli game --mode DF_NRM "C:\dump\rock"

# 模糊匹配（后缀不用完全相等）
python -m dayz_texture_tool.cli game --auto --match fuzzy "C:\dump\rock"
```

### 5.2 `pbr` —— PBR2DayZ

按「文件夹 + 前缀」把贴图归组，每组打包成 DayZ 的贴图。

```bash
python -m dayz_texture_tool.cli pbr [选项] PATH [PATH ...]
```

| 选项 | 说明 |
| --- | --- |
| `--normal {directx,opengl}` | 法线约定，默认 `directx` |
| `--resolution {auto,256,512,1024,2048}` | 输出分辨率，默认 `auto` |
| `--prefix-mode {...}` | 前缀规则：`auto` `current_folder` `parent_folder` `filename_prefix` `custom`，默认取设置 |
| `--custom-prefix STR` | `--prefix-mode custom` 时用的前缀，默认取设置 |
| `--match {exact,fuzzy}` | 文件名归类方式，默认取设置里的 `pbr_match_mode`（默认 `fuzzy`） |
| `--co-mode STR` | CO 图怎么出：`basecolor`（默认，直接搬颜色）或 `specular`（用金属度图做高光分离） |
| `--specular FLOAT` | SMDI 高光强度，默认 `0.75` |
| `--glossiness FLOAT` | SMDI 光泽度，默认 `1.0` |
| `--paa` / `--no-paa` | 是否转成 PAA，**默认开** |
| `--watermark` / `--no-watermark` | 顺带加水印，默认关 |
| `--watermark-content STR` | 水印文字，默认取设置 |
| `--watermark-password STR` | 水印密码，默认取设置 |
| `--delete-source` | 处理完把源文件丢进回收站，默认关 |

**输入类型**按关键词识别：颜色、法线、粗糙度、金属度、AO。**输出**：`_co`、`_nohq`、`_smdi`、`_as`。

一组可以有 1 到 5 张源图 —— **只有存在的那几种类型才会生成对应输出**。

```bash
python -m dayz_texture_tool.cli pbr --no-paa --watermark --watermark-content "我的模组" "C:\dump\wall"
```

### 5.3 `watermark` —— 水印

基于 `blind-watermark` 的不可见盲水印。嵌进去之后图片肉眼完全一样，之后凭密码和水印长度还原。

```bash
python -m dayz_texture_tool.cli watermark [选项] PATH [PATH ...]
```

| 选项 | 说明 |
| --- | --- |
| `--mode {embed,detect}` | 加还是查，默认 `embed` |
| `--content STR` | 水印文字，**加的时候必填**，默认取设置 |
| `--password STR` | 密码，默认取设置 |
| `--length N` | 水印位数，**查的时候必填**（要大于 0），默认取设置 |
| `--overwrite` | 直接写回源文件，默认关（默认另存为 `xxx_watermarked.tga`） |

加和查分两个动作：

```bash
# 加
python -m dayz_texture_tool.cli watermark --content "my mod" "C:\dump"

# 查（length 用加的时候报出来的那个值）
python -m dayz_texture_tool.cli watermark --mode detect --length 15 "C:\dump"
```

加水印之后，结果里会带一个 `watermark_length`，就是下次查的时候要填的位数。

### 5.4 `smdi` —— SMDI

一张颜色贴图进去，一张高光图出来。

```bash
python -m dayz_texture_tool.cli smdi [选项] PATH [PATH ...]
```

| 选项 | 说明 |
| --- | --- |
| `--specular FLOAT` | 高光强度，默认取设置（默认 `10.0`） |
| `--paa` / `--no-paa` | 出 `.paa` 还是 `.tga`，**默认出 PAA** |

```bash
python -m dayz_texture_tool.cli smdi --specular 12.5 "C:\dump\rock_co.tga"

# 不想转 PAA
python -m dayz_texture_tool.cli smdi --no-paa "C:\dump\rock_co.tga"
```

### 5.5 `rvmat` —— RVMAT

一个材质进去，最多三个磨损变体出来。

```bash
python -m dayz_texture_tool.cli rvmat [选项] PATH [PATH ...]
```

| 选项 | 说明 |
| --- | --- |
| `--variants LIST` | 要哪几个，逗号分隔，从 `worn` `damage` `destruct` 里挑，默认三个都要 |
| `--damage-texture NAME=PATH` | 换掉某个变体的 Stage3 贴图，可重复 |

```bash
# 只要磨损版
python -m dayz_texture_tool.cli rvmat --variants worn "C:\dump"

# 换掉磨损版的贴图
python -m dayz_texture_tool.cli rvmat --damage-texture worn=dz\characters\data\worn_mc.paa "C:\dump"
```

### 5.6 `settings` —— 读写设置

```bash
python -m dayz_texture_tool.cli settings path            # 设置文件在哪
python -m dayz_texture_tool.cli settings list            # 全部设置
python -m dayz_texture_tool.cli settings get KEY         # 读一个
python -m dayz_texture_tool.cli settings set KEY VALUE   # 写一个
```

KEY 支持用点往下钻：

```bash
python -m dayz_texture_tool.cli settings get pbr_output_suffixes.co      # 输出 _co
python -m dayz_texture_tool.cli settings set pbr_output_suffixes.co _custom
```

`set` 会先检查值和字段类型、允许的取值是否对得上；如果原来那个文件已经不是合法的 JSON，它**宁可报错也不会写**——绝不会把你的配置默默换成默认值。

值的写法按字段类型自动判断：数字写 `12.5`，布尔写 `true` / `false`，对象和数组写 JSON，字符串直接写。

### 5.7 `gui` —— 打开界面

```bash
python -m dayz_texture_tool.cli gui
```

只有这个子命令会加载界面库。其他子命令不碰 Qt，所以在没有显示器的机器上也能用。

---

## 六、`--dry-run` 是怎么算的

加上之后**一个文件都不写**，只报告「打算做什么」。

JSON 里的状态换了一套词：

| 状态 | 意思 |
| --- | --- |
| `planned` | 会处理，产出列在 `outputs` 里 |
| `planned-skip` | 会跳过（后缀对不上、已经是生成物、没有可转换的贴图等），原因在 `messages` 里 |
| `invalid` | 路径不存在，或扩展名不支持 |

`summary` 也跟着换成 `planned` / `planned-skip` / `invalid` 三项计数，`elapsed_ms` 统一填 `0`。

`--dry-run` 时 `--strict` 无效。

---

## 七、JSON 输出

加 `--json` 之后，标准输出只有**一个** JSON 对象：

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

`status` 在正常运行时是 `success` / `skipped` / `failed` 三种；`--dry-run` 时换成第六节那三种。

`metadata` 里可能有的东西：加水印时是 `watermark_length`。

**`settings` 子命令不走这个信封**，它的输出就是那个值本身：

| 命令 | 输出 |
| --- | --- |
| `settings path` | 一行路径 |
| `settings list` | 整个配置对象 |
| `settings get KEY` | 那个键的值（配 `--json` 时是 JSON 编码的，字符串会带引号） |
| `settings set KEY VALUE` | `KEY = VALUE` 一行确认 |

---

## 八、和界面的三处不同

这三处是**有意**做成不一样的，不是 bug。

1. **文件夹一律往里翻。** 界面里只有 Game2PBR、PBR2DayZ、RVMAT 会这样，水印和 SMDI 不会。
2. **`--delete-source` 默认关。** 界面里是开着的。命令行上误删的代价太大，所以反过来。
3. **手动指定 `--mode` 时不按后缀筛文件。** 界面里会把跟当前处理器对不上的行藏起来；命令行上你点了名的文件都会处理。想让它自己判断该用哪个处理器，用 `--auto`。

---

## 九、设置文件里有哪些键

用 `settings list` 看全部。常用的：

| 键 | 类型 | 默认 | 对应哪个开关 |
| --- | --- | --- | --- |
| `image_to_paa` | 字符串 | 空 | `ImageToPAA.exe` 的位置 |
| `language` | 字符串 | `en` | 界面语言 |
| `theme` | 字符串 | `dark` | 界面主题，`dark` 或 `light` |
| `game_match_mode` | 字符串 | `exact` | `game --match` |
| `pbr_match_mode` | 字符串 | `fuzzy` | `pbr --match` |
| `pbr_prefix_mode` | 字符串 | `auto` | `pbr --prefix-mode` |
| `pbr_custom_prefix` | 字符串 | 空 | `pbr --custom-prefix` |
| `watermark_content` | 字符串 | 空 | `watermark --content` |
| `watermark_password` | 字符串 | `1` | `watermark --password` |
| `watermark_length` | 整数 | `0` | `watermark --length` |
| `smdi_specular_power` | 小数 | `10.0` | `smdi --specular` |
| `game_suffixes` | 对象 | 见 `settings list` | `game --auto` 靠它分发 |
| `game_output_suffixes` | 对象 | 见 `settings list` | 各模式的输出后缀 |
| `pbr_suffixes` | 对象 | 见 `settings list` | PBR 输入类型关键词 |
| `pbr_output_suffixes` | 对象 | `co/nohq/smdi/as` | PBR 输出后缀 |
| `rvmat_damage_textures` | 对象 | 三个 `dz\characters\...` 路径 | 各变体的默认贴图 |
| `rvmat_excluded_suffixes` | 数组 | `_worn` `_damage` `_destruct` | 哪些文件不当作源 |
| `last_page`、`window_geometry` | — | — | 界面自己记的状态，命令行用不到 |

改 `game_suffixes` / `game_output_suffixes` / `pbr_suffixes` 这类对象时，**写进去的内容会和默认值合并**，不是整个替换。所以只想改一项的话，只写那一项就行。

---

## 十、关于 PAA

有些地方要用到 `ImageToPAA.exe`（DayZ Tools 自带，Steam 上免费）：

- `smdi --paa`、`pbr --paa` 要生成 PAA 时
- 输入或输出是 `.paa` 时（比如水印、SMDI 处理 `.paa`）

**找不到它会直接报错退出（退出码 2），不会偷偷降级。** 这是故意的：宁可明确告诉你缺东西，也别让你以为生成了 PAA 结果其实没有。

不想用 PAA，加 `--no-paa`（`pbr` 和 `smdi` 都有）。

---

## 十一、常见坑

### 11.1 同一个文件夹重复跑同一个命令

第一次跑完，`rock_df_nrm_Metal.png` 这些产物就躺在源文件旁边了。第二次再对**同一个文件夹**跑同样的命令，这些产物会被当成输入，于是报错：

```
[FAIL] ...\rock_df_nrm.tga -> Output rock_df_nrm_Metal.png would overwrite another input file in this batch.
```

退出码 1。目前的做法是**先报错、不写文件**，不会闷头覆盖。

想重跑，把源文件单独指出来（而不是给整个文件夹）：

```bash
python -m dayz_texture_tool.cli game --mode DF_NRM "C:\dump\rock\rock_df_nrm.tga"
```

或者先把上一次的产物挪走。

### 11.2 显式 `--mode` 会连产物一起处理

因为第八节第 3 条，`game --mode DF_NRM <文件夹>` 会把文件夹里**所有**图片都按 DF_NRM 处理一遍，包括上一次跑出来的 `rock_df_nrm_Metal.png`。结果是 `rock_df_nrm_Metal_Metal.png` 这种没意义的东西。

给文件夹时优先用 `--auto`，它只处理后缀能对上输入模式的文件。

### 11.3 同名会被直接覆盖

没有「跳过已存在」这个选项，产物就是直接覆盖。第一次跑之前先 `--dry-run`。

### 11.4 路径跨盘符

`pbr` 需要把一组贴图归到一起，所以要求所有输入在同一个盘上。跨盘符会报错退出 2。

---

## 十二、给脚本 / AI 用的小抄

```bash
# 想拿机器可读的结果：加 --json，读 stdout，看 summary 和 results
python -m dayz_texture_tool.cli --json game --auto "C:\dump\rock"

# 想知道会做什么、又不冒险：加 --dry-run
python -m dayz_texture_tool.cli --json --dry-run game --auto "C:\dump\rock"

# 只关心成功与否：看退出码（0 成功 / 1 有失败 / 2 用法错）
python -m dayz_texture_tool.cli --quiet game --auto "C:\dump\rock" && echo OK

# 一个都没成功也算失败
python -m dayz_texture_tool.cli --strict --quiet game --auto "C:\dump\rock"

# 用临时配置跑，不动用户的设置文件
python -m dayz_texture_tool.cli --settings "C:\tmp\s.json" --json game --auto "C:\dump\rock"
```

几条要点：

- 结果在 **stdout**，进度在 **stderr**，两者不会混。
- JSON 只有 ASCII，中文路径是 `\uXXXX` 转义，任何代码页都能读。
- 每个开关的默认值都来自 `settings.json`，命令行上写了的优先。
- 全局开关放子命令前面或后面都行。
- 拿不准就先 `--dry-run`。
- **文本输出用的是控制台编码，不是 UTF-8**（分隔符 `·` 不是 ASCII）。程序解析请用 `--json`，不要抓文本。
