# DayZ 贴图工具 · Qt 界面迁移计划

> 状态：**已完成**。十步全部跑完，全量测试 90 个用例通过，出包 269 MB，双击能跑。
> 实施时发现并记下的差异，写在各节末尾的“实施补记”里。
> 样张：`build/mockup/` 下 8 张，1440×900，都是真 Qt 渲染出来的，不是示意图

---

## 一、这件事要做成什么样

把现在这个界面（customtkinter + tkinterdnd2，1055 行挤在一个文件里）**整个换掉**，改成 Qt 做的界面，形状是：

```
┌────────────┬──────────────────────────────────────────────────────┐
│ DayZ 贴图工具 │  Game2PBR                                            │
│            ├──────────────────────────────────────────────────────┤
│ ▸ Game2PBR │ [处理模式 ▾] [精准匹配] [删除原图] [按后缀全选] [＋ 添加 ▾] │
│   PBR2DayZ ├──────────────────────────────────────────────────────┤
│   水印      │ 文件      变换前   变换后            尺寸/大小   状态    │
│   SMDI     │ ──────────────────────────────────────────────────── │
│            │ ☑ a_nrm.tga [原图]→[Metal][Rou][N]  2048²  ● 完成     │
│            │ ☑ b_nrm.tga [原图]→[Metal][Rou][N]  2048²  ● 处理中   │
│            │ ☐ c_nrm.tga [原图]→ 未生成输出       ——     ● 失败     │
│ ────────── │                                                      │
│ ⚙ 设置      ├──────────────────────────────────────────────────────┤
│ 文 中 / EN  │ 共 5 个 · 完成 1 · 跳过 1 · 失败 1  62% [═══════] [开始处理] │
└────────────┴──────────────────────────────────────────────────────┘
```

**一行 = 一次执行**。左边是进的东西（1 张图，或者 PBR2DayZ 那样 5 张一组），箭头，右边是这次执行产出的所有图，每张下面带名字（`Metal` / `Rou` / `N` / `_co` / `_smdi`…）和文件大小。最右边是尺寸、大小变化、状态。

列的宽度按页面固定（Game2PBR 的"变换前"是 1 格，PBR2DayZ 是 5 格），所以**同一页里箭头和后面的列永远在同一个横坐标上**，表头能对齐。

---

## 二、明确不做的事

| 不做 | 原因 |
|---|---|
| 改任何图片处理算法 | 你定的：只换界面。`processors/`、`batch.py`、`models.py`、`settings.py` 的处理逻辑一行不动 |
| 换设置文件的格式和位置 | 还是 `%APPDATA%\Roaming\DayZ_Texture_Tool\settings.json`，你现有的配置直接能用 |
| 中途停止 / 多任务并行 | 现在没有，这版也不加 |
| 自动判断该用哪个处理模式 | `batch.py` 里其实**已经有一个**（`batch.py:38 detect_game2pbr_processor`、`batch.py:65 process_game2pbr_auto`），但它只认 `_nrm`/`_mra`/`_orn` 三种后缀，旧界面根本没接线。要接就得扩到 9 种，猜错会静默产出错的图——这版先不接，保持“手动选模式” |
| 列表排序 / 筛选 / 搜索 | 一次几十张，用不上 |
| 皮肤库（qdarkstyle / qt-material / Fluent-Widgets） | 它们自带一套颜色，会把我们定的中性灰换掉；Fluent 还是 GPLv3 |
| 自己画图标 | 用现成的 `qtawesome`（MIT，一万个图标） |
| 自己写翻译查找层 | 用 Qt 自带的翻译系统 |

---

## 三、技术选型

| 用什么 | 版本 | 授权 | 为什么 |
|---|---|---|---|
| **PySide6-Essentials** | 6.12.0 | LGPL-3.0（可闭源） | 你的另一个工具 `DayZ_Translate_Tool` 已经用 PySide6 + PyInstaller 出过包，这条路在你机器上跑通过。装 Essentials 而不是完整版，是为了不带用不上的 WebEngine（131 MB） |
| **qtawesome** | 1.4.2 | MIT | 图标库。只拖一个依赖 `qtpy` |
| 拖拽 | — | — | Qt 原生支持，**不再需要 tkinterdnd2** |

不冲突：Qt 的依赖跟 numpy / Pillow / opencv / blind-watermark 完全不相交，装的时候不会动现有任何一个包。

体积：现在 one-folder 185 MB，迁移后估计 **220–280 MB**。

---

## 四、视觉规范（已经定稿）

### 颜色

```
BG_SHELL     #181818   侧边栏、底部状态栏（外壳，比内容面暗一档）
BG_CONTENT   #1e1e1e   内容区底
BG_ROW_HOVER #242424   行悬停
BG_WELL      #2a2a2a   缩略图底槽
BG_WELL_IN   #313131   输入图的底槽（比输出亮一档，强调"源头"）
BG_BTN       #2d2d2d   普通按钮        BG_BTN_HOVER #383838
BG_FIELD     #232323   输入框
LINE         #2a2a2a   分隔线          LINE_STRONG  #3a3a3a
TEXT         #ececec   正文            TEXT_DIM     #b4b4b4
TEXT_MUTED   #8c8c8c   次要信息（对 #1e1e1e 的对比度 4.97:1，过了 4.5:1 的地板）
ACCENT       #29f7ff   青 —— 只用在三处：当前选中的侧边栏项 / 主操作按钮 / 进度条
ACCENT_INK   #0d1416   青底上的字
OK #3fb950   ERR #f85149   SKIP #8c8c8c
```

**为什么是中性灰不是彩色**：这个工具是用来判断贴图颜色的，界面自己带颜色会骗眼睛。Photoshop、达芬奇在图片周围一律用中性灰，同一个道理。颜色额度全留给贴图本身。

### 字号（固定，不随窗口缩放）

```
11pt 加粗   页面标题
9.5pt 加粗  区块标题（"问题 3 条"、设置页的分组名）
9pt         正文、按钮、列表内容
8.5pt       次要信息（尺寸、提示）
8pt         缩略图名、列表表头
7.5pt       最小字（文件大小、状态备注）
```

字体：`Microsoft YaHei UI`。加粗只用在标题上。

### 尺寸

```
窗口默认 1440×900，最小 1100×700，记住上次的大小和位置
侧边栏 200px      侧边栏项高 38px      行高 112px
缩略图 70px 宽（图 64×64 + 名字 + 大小三行）
工具条控件高 30px     列表表头高 32px     底部状态栏高 46px
底部进度条 360px 宽，「开始处理」按钮在最右下角（整页唯一一个青色按钮）
内容区左右边距 22px   行内左右边距 12/16px
圆角 4px（按钮、输入框），6px（卡片、浮层）
```

### 不用的东西（这几条是硬规矩）

- 标题上面不放假的小标签（kicker / eyebrow）
- 不用渐变文字
- 不叠卡片（卡片里套卡片）
- 不为了"好看"加动画；动效只用来表达状态变化，150–250ms
- 不用 emoji 或 Unicode 符号冒充图标
- 加载时用空底槽（骨架），不在内容中间转圈

---

## 五、文件清单

### 不动（业务逻辑，一行不改）
```
src/dayz_texture_tool/models.py           59 行
src/dayz_texture_tool/recycle.py          37 行
tests/test_game2pbr.py · test_pbr2dayz.py · test_smdi.py · test_watermark.py · test_batch_settings.py
```

### 微改 1：只加字段，不加逻辑
```
src/dayz_texture_tool/settings.py        113 行 → 加 3 个字段
```
`AppSettings` 现在有 14 个字段（image_to_paa / language / game_suffixes / game_output_suffixes / pbr_suffixes / pbr_output_suffixes / pbr_prefix_mode / pbr_custom_prefix / game_match_mode / pbr_match_mode / watermark_content / watermark_password / watermark_length / smdi_specular_power）。
新界面有三样东西要记住：**主题（深/浅）· 上次停在哪个功能 · 窗口大小和位置**。所以要加 `theme` / `last_page` / `window_geometry` 三个字段，**只加字段，不加任何逻辑**。
`load_settings` 是 `{**asdict(AppSettings()), **data}` 合并的，**旧配置文件照样能读**，缺的键自动补默认值，不用做迁移。

### 微改 2：只给提示文字套一层翻译壳，处理逻辑不动
```
src/dayz_texture_tool/batch.py                      6 处
src/dayz_texture_tool/processors/game2pbr.py        3 处
src/dayz_texture_tool/processors/pbr2dayz.py        9 处
src/dayz_texture_tool/processors/smdi.py            4 处
src/dayz_texture_tool/processors/watermark.py       8 处
```
共 30 处，其中 **5 处是 `f"{type(exc).__name__}: {exc}"` 这种异常转文字——这些不翻**（把 Python 异常名翻译成中文没意义，反而查不到资料），分别位于 `processors/game2pbr.py:198`、`processors/pbr2dayz.py:298`、`processors/smdi.py:131`、`processors/watermark.py:129`、`processors/watermark.py:173`。剩 **25 处**要套壳，实施时逐条过一遍别漏。

改法：`"Skipped ...: no matching suffix."` → `QCoreApplication.translate("Batch", "Skipped %1: no matching suffix.").replace("%1", name)`
**没有装翻译文件时，这层壳原样返回英文**（已实测），所以现有 81 个测试断言什么还断言什么，全部不受影响。
⚠️ 实现时注意：这层壳**不能看 `settings.language`**（`settings.py` 里默认是 `"zh"`）。它必须只看装没装翻译器，否则测试会挂。

### 微改 3：改一个函数名（函数体一行不动）
```
src/dayz_texture_tool/processors/pbr2dayz.py   105 行 `_scan_pbr_paths` → `scan_pbr_paths`（2 处：定义 + 内部调用）
src/dayz_texture_tool/processors/__init__.py   导出列表里加一行
```
理由：新界面要在**处理之前先把“组”画到列表里**。拖文件夹时用现成的公开函数 `scan_pbr_groups`（`pbr2dayz.py:124`），拖一堆文件时得用 `_scan_pbr_paths`（`:105`）——它现在是私有名。只改名字，不碰一行逻辑。

### 微改 4：被牵连的文件
```
src/dayz_texture_tool/ui/__init__.py        4 行 —— 现在写着 `from .main_window import DayZTextureToolApp`，删掉 main_window.py 后不改就直接 ImportError
requirements.txt                            customtkinter / tkinterdnd2 → PySide6-Essentials / qtawesome
pyproject.toml                              同上（dependencies 里那两行）
DayZ_Texture_Tool.spec                      `collect_all("customtkinter")` / `collect_all("tkinterdnd2")` 换成 PySide6 的 hook
scripts/package.ps1                         装包那一步的包名
```

### 删掉
```
src/dayz_texture_tool/ui/main_window.py     1055 行旧界面
src/dayz_texture_tool/ui/i18n.py            230 行旧翻译表（内容会先自动转成 .ts 再删）
tests/test_ui_dragdrop.py                   12 个测试（给 tkinter 写的，整体失效）
```

### 新增
```
src/dayz_texture_tool/app.py                [改写] 入口：装翻译器 → 建窗口
src/dayz_texture_tool/ui/theme.py           [新] 调色板、字号、全局样式表、深浅两套
src/dayz_texture_tool/ui/icons.py           [新] qtawesome 封装（6 个图标名集中在这）
src/dayz_texture_tool/ui/thumbs.py          [新] 缩略图异步加载 + 缓存
src/dayz_texture_tool/ui/session.py         [新] 待处理列表的记忆
src/dayz_texture_tool/ui/widgets/sidebar.py [新]
src/dayz_texture_tool/ui/widgets/toolbar.py [新] 下拉框/开关/分段按钮/输入框 四个控件
src/dayz_texture_tool/ui/widgets/row.py     [新] 一行
src/dayz_texture_tool/ui/widgets/list_view.py  [新] 表头 + 行列表 + 空状态
src/dayz_texture_tool/ui/widgets/status_bar.py [新] 状态 + 进度
src/dayz_texture_tool/ui/widgets/issues_panel.py [新] 问题面板
src/dayz_texture_tool/ui/widgets/lightbox.py   [新] 大图浮层
src/dayz_texture_tool/ui/pages/base.py      [新] 页面基类
src/dayz_texture_tool/ui/pages/game2pbr.py  [新]
src/dayz_texture_tool/ui/pages/pbr2dayz.py  [新]
src/dayz_texture_tool/ui/pages/watermark.py [新]
src/dayz_texture_tool/ui/pages/smdi.py      [新]
src/dayz_texture_tool/ui/pages/settings.py  [新]
src/dayz_texture_tool/translations/dayz_texture_tool_zh.ts  [新] 英文原文 → 中文译文
src/dayz_texture_tool/translations/dayz_texture_tool_zh.qm  [新，构建产物，提交进仓库]
tests/test_ui_pages.py                      [新] 替代旧的 test_ui_dragdrop.py
docs/DESIGN.md                              [新] 完工时写：这一版界面的设计契约
```

---

## 六、五个页面各有什么

### 侧边栏（所有页面共用）
- 顶部：`DayZ 贴图工具`
- 四个功能：Game2PBR / PBR2DayZ / 水印 / SMDI（当前选中的项：左侧 3px 青条 + 稍亮的底）
- 撑开后底部分隔线 → `设置` → `中 / EN`
- **打开软件停在上次用的那个功能**

**底部状态栏（所有页面共用）**：左边是状态文字，右边依次是百分比、360px 长的进度条、以及整页**唯一一个青色主按钮 `开始处理`**（在最右下角）。工具条里没有主按钮。

**列表（所有页面共用）**：每一行最左边有个勾选框，表头最左边也有一个全选勾选框。**勾上的行才会被处理**——旧界面那三个按钮在新界面里是这样对应的：

| 旧界面 | 新界面 |
|---|---|
| `清除选中` | 点一下表头的全选框，取消勾选 |
| `处理选中` | 留几个勾着，点右下角 `开始处理` |
| `处理全部` | 点表头全选框勾上，再点 `开始处理` |

旧界面的 `选择文件` / `选择文件夹` 两个按钮合并成工具条右边的 `＋ 添加 ▾`（一个下拉，里面两项）。

**识别后缀提示**：旧界面在后缀框旁边有一行实时提示（“当前按 `_nrm` 匹配”），新界面保留这个信息，但放在两个地方：空列表时的大字提示里，以及状态栏左边。

### 1. Game2PBR
工具条：`处理模式 ▾`（9 种，每个选项后面标它自己出几张：1 / 2 / 3 / 4 张）· `精准匹配 / 模糊匹配` · `删除原图` 开关 · `按后缀全选` · `＋ 添加 ▾`

列表：1 张进 → N 张出（N 由模式决定：拆分 RGBA 出 4 张，DF_NRM 出 3 张，直接转换出 1 张…）

### 2. PBR2DayZ
工具条：`法线 directx / opengl` · `分辨率 ▾`（自动/256/512/1024/2048）· `前缀：自动识别 ▾` · 自定义前缀输入框 · `精准 / 模糊` · `生成 PAA` · `添加水印` · `删除原图` · `＋ 添加 ▾`

列表：按「同一个文件夹 + 同一个前缀」成组，**一组 1–5 张都行**（`_basecolor` / `_normal` / `_roughness` / `_metallic` / `_ao` 里有哪些算哪些），有几张就显示几张缩略图；每组最多出 4 张（`_co` / `_nohq` / `_smdi` / `_as`），**只有组里存在的类型才会生成对应那一张**，缺的类型在输出那一栏留个灰底槽并标“无”。
一组里一张能用的都没有 → 这一行显示“已跳过：没有可转换的贴图”（这是 `processors/pbr2dayz.py` 的现有行为，不是新加的）。

> 注：旧界面的 PBR2DayZ 页其实是**扁平文件列表**（一个文件一行），根本没有"组"的概念。"按组显示"是这一版新加的，分组本身靠现有函数算：拖文件夹时用 `scan_pbr_groups`（`src/dayz_texture_tool/processors/pbr2dayz.py:124`，已经是公开的），拖一堆文件时用 `_scan_pbr_paths`（`:105`，**现在是私有的**）。后者只需要**去下划线改成公开名**（见“五、文件清单 → 微改 3”），**函数体一行不动**。

这一页的工具条控件最多，**已经量过宽度**（`build/mockup/measure.py`，用真实控件算的）：中文 1014px、英文 1015px，1440 窗口下可用 1196px，还剩 181px 余量，**不用折行、不用藏控件**。

### 3. 水印
工具条：`嵌入 / 检测`（模式切换）· `内容` · `密码` · `长度` · `覆盖原图` · `＋ 添加 ▾`

- 切到"检测"时，`内容` / `长度` / `覆盖原图` 三个框**留在原位但变灰**（不隐藏——隐藏会让工具条忽长忽短，每换一次模式就得重新找东西在哪）
- 列表：左边是原图缩略图，右边那栏**不显示图片**（盲水印处理前后肉眼一模一样），显示文字：`已嵌入水印` / `嵌入中…` / `未嵌入`。表头那栏叫"结果"
- **水印内容 / 密码从设置页搬到这里**（旧界面它们在设置页，水印页反而没有）
- 旧界面“检测”成功之后会把检测到的水印长度**回填到长度框**里，这个联动保留

### 4. SMDI
工具条：`高光强度` 输入框 · `生成 PAA` 开关 · `＋ 添加 ▾`

列表：1 张进 → 1 张出

### 5. 设置（整页，不弹窗）
三张卡片，可滚动：

1. **通用**：界面语言 · 主题（深色/浅色）· ImageToPAA 路径 + `浏览…`
2. **Game2PBR · 处理模式后缀**：9 行，每行 = 处理模式 / 识别后缀 / 生成贴图后缀（按槽位分几个框）。内容跟 `settings.py` 里现有的 9 组一一对应，**一个不多一个不少**
3. **PBR2DayZ · 成组关键词与输出后缀**：5 行关键词（底色/法线/粗糙/金属/环境光）+ 1 行输出后缀（`_co`/`_nohq`/`_smdi`/`_as`）

底部状态栏：`设置已自动保存`（不设"保存"按钮，改完立刻存）

**后缀校验（旧界面有，新界面必须保留）**：旧界面在开跑前会查两件事（`src/dayz_texture_tool/ui/main_window.py:985 _suffix_error`，调用点 `:901` Game2PBR、`:926` PBR2DayZ）——① 后缀里不能带 `.`；② 同一组后缀不能重复（重复会让输出互相覆盖）。新界面把校验从"开跑前弹错"改成**在设置页的输入框旁边当场标红**，但规则一模一样。
另外两个细节：
- "直接格式转换模式"的输出后缀默认是**空字符串**（`settings.py` 里 `"converted": ""`），**空框是合法的**，不能当成错误
- 后缀框里的输入允许用逗号/空格分隔多个值（旧界面的 `_parse_suffix_text` 就是这个行为），设置页要用同样的解析规则

---

## 七、几件要单独说清楚的事

### 1. 参数放哪：工具条 vs 设置页
规则：**工具条 = 每批文件都可能要改的；设置页 = 配一次能用很久的。**
所以"识别后缀""生成贴图后缀""成组关键词"这些全部搬进设置页——它们现在的数据层已经按处理模式分开存了，纯粹是界面搬迁，`settings.json` 的格式不变。

### 2. 翻译
- **软件默认是英文，所以英文原文直接写在代码里**当原文（`self.tr("Start")`），`.ts` 文件里放对应的中文
- 好处：默认的英文界面永远不可能因为"漏翻"而破掉（原文直接显示，缺了就显示英文）；中文靠 Qt 的 `lupdate` 自动收集，漏了会自己报出来（这是继续用旧字典表最大的问题——漏翻是静默的）
- **为什么原文必须是英文而不是中文**：如果反过来（中文当原文、英文当译文），默认的英文界面一旦漏翻就会掉回中文——正好是一开始要消灭的那种错。**原文语言必须等于默认语言**
- 现有的 **110 条**译文条目（`src/dayz_texture_tool/ui/i18n.py` 里 `TEXTS['zh']` 和 `TEXTS['en']` 各 110 条，两边 key 完全对称；里面本来就有一部分值是英文或空串，比如 `"watermark": "Watermark"`），**写脚本一次性转进 `.ts`**，一条不丢
- 运行时切中英文不重启
- Qt 自带的对话框（打开文件、右键菜单）另外挂 PySide6 自带的 `qt_zh_CN.qm`
- `.qm` 生成一次后提交进仓库，打包时不需要翻译工具

### 3. 缩略图
- 用 `QImageReader.setScaledSize` 按 64px 读，不是读全图再缩
- 只算**屏幕上看得见的行**，后台线程慢慢补其余的
- 没算完时显示空底槽（不是转圈）
- 结果进 `QPixmapCache` 缓存
- 读不出来的文件（比如某些 DDS）显示中性占位块 + 后缀名，不是空白

### 4. 大列表不卡
- 用 `QListView` + 自定义模型 + 自定义绘制，**不用 QListWidget**（那个每行建一个对象，几千行会卡）
- 开 `setUniformItemSizes(True)` 和 `setLayoutMode(Batched)`
- 设计按 50 张做，但要保证 500 张不垮——这一条会实测

### 5. 待处理列表的记忆
- 每次列表变动**悄悄存一份**到 `%APPDATA%\Roaming\DayZ_Texture_Tool\session.json`（节流，最多每秒一次）
- **正常关闭时删掉**
- 所以只有崩溃、断电、任务管理器强杀之后，下次打开才会看到残留——这是它的用途

### 6. 处理怎么跑
- 处理在后台线程跑（Qt 的 `QThreadPool`），通过信号把进度发回界面，界面不卡
- 这一版**不加中途停止**（跟现在一致）

---

## 八、分几步做，每步怎么验证

| 步 | 做什么 | 怎么验证 |
|---|---|---|
| 0 | 装 PySide6-Essentials + qtawesome；建 `theme.py`、`icons.py`；`app.py` 改成能起一个空窗口 | 跑起来是一个 1440×900 的深色空窗口，`.venv` 里 `pip check` 干净 |
| 1 | 侧边栏 + 5 个空页面 + 底部状态栏，能切换 | 点侧边栏换页，选中项是青条；窗口大小位置能记住 |
| 2 | 列表（表头 / 行 / 空状态）+ 缩略图加载，先用假数据 | 塞 500 行假数据，滚动不卡；缩略图逐张出现不闪 |
| 3 | Game2PBR 页接真逻辑：拖拽、添加、开始处理、进度、状态 | 拿真贴图跑一遍，**输出文件跟旧界面跑出来的完全一致** |
| 4 | PBR2DayZ 页 | 一组 PBR 贴图跑出 4 张；一组只给 3 张时只出 3 张、缺的那栏标“无”；一组一张能用的都没有时显示“已跳过：没有可转换的贴图” |
| 5 | 水印页 + SMDI 页 | 嵌入后能检测出来；SMDI 输出跟旧的一致 |
| 6 | 设置页（9 行后缀表 + 关键词 + 输出后缀 + 路径 + 语言 + 主题） | 改一个后缀 → 存进 `settings.json` → 重启还在；换处理模式时对应的后缀跟着换 |
| 7 | 翻译：`lupdate` 生成 `.ts` → 填中文 → `lrelease` 生成 `.qm` → 接进 app | 切中英文，整个界面都变，不重启；**中文下找不到一条漏翻的英文**（默认的英文界面不需要翻译器，永远不会破） |
| 8 | 细节状态：空列表、问题面板、大图浮层、浅色主题 | 逐张对照 `build/mockup/` 里的样张 |
| 9 | 删旧界面和旧翻译表；重写 UI 测试；改打包脚本 | 全部测试通过；出一个包，双击能跑，五页都点一遍 |

---

## 九、测试怎么办

- 逻辑层的 69 个测试（game2pbr 12 + batch_settings 10 + pbr2dayz 18 + **smdi 19** + watermark 10 = 69）**全部原样保留、必须全绿**。这是"业务逻辑没被动过"的证明
- 旧的 `tests/test_ui_dragdrop.py`（12 个）**整体失效**——它是给 tkinter 写的，直接调未绑定方法、造假事件。参照它的思路重写成 `tests/test_ui_pages.py`：
  - 拖拽进来一批文件 → 列表里出现正确的行数和分组
  - 切换处理模式 → 后缀框跟着换
  - 点击开始 → 调用了正确的处理函数、参数对得上
  - 跳过和失败分开计数
  - 语言切换后文案真的变了
- 测试用 `QApplication` 但**不显示窗口**（`QT_QPA_PLATFORM=offscreen`），跟现在"不创建真窗口"的做法一致

---

## 十、打包怎么办

- `DayZ_Texture_Tool.spec`：把 `collect_all("customtkinter")` / `collect_all("tkinterdnd2")` 换成 PySide6 的 hook（PyInstaller 自带），加 `qtawesome` 的图标字体和 `.qm` 文件
- `scripts/package.ps1`：`requirements.txt` 里 `customtkinter` / `tkinterdnd2` 换成 `PySide6-Essentials` / `qtawesome`；跑测试那一步不变
- 注意：PyInstaller 会**阻止同时打包 PyQt6 和 PySide6**，我们只用 PySide6，没问题
- 体积会从 185 MB 涨到 220–280 MB

---

## 十一、已知的代价和风险

| 风险 | 说明 | 怎么办 |
|---|---|---|
| 包变大 40–95 MB | PySide6 自带的 Qt 库 | 只装 Essentials，不带 WebEngine |
| 第一次启动变慢 | Qt 库要加载 | 实测；如果超过 3 秒再想办法 |
| 某些 DDS 缩略图读不出来 | Pillow 对 DDS 支持有限 | 显示占位块 + 后缀名，不空白 |
| 逻辑层多一个 Qt 依赖 | 提示文字套翻译壳的代价 | 只用到 `QCoreApplication.translate`，不建窗口，测试照跑 |
| `.ts` 是 XML，手改不如 Python 字典舒服 | Qt 的标准做法 | 有官方图形编辑器 Qt Linguist |
| 旧界面删掉后没法回退 | 你确认过不需要保留双份 | git 里有历史，随时能翻回来 |

---

## 十二、做完之后你怎么验证

1. 双击跑起来 → 是不是深色的、侧边栏在左、列表是大列表
2. 打开软件 → 是不是停在上次用的那个功能
3. 拖一批贴图进去 → 是不是按后缀自动分了组、缩略图逐张出现
4. 点"开始处理" → 每行状态变绿打勾、底部进度条走、有问题的进"问题"面板
5. **拿旧界面跑同一批文件，对比输出** → 文件应该完全一样
6. 点一个缩略图 → 弹出大图，能左右切换
7. 设置页改一个后缀 → 关掉软件再打开，还在
8. 侧边栏底部切中英文 → 整个界面都变，不重启
9. 设置里切浅色 → 变成一套中性浅灰（不是把深色反过来）
10. 出包 → 双击 `release\` 里的 exe 能跑

---

## 附：样张清单

`build/mockup/` 下 8 张，都是真 Qt 渲染的 1440×900：

```
mockup_game2pbr.png    Game2PBR 主界面
mockup_pbr2dayz.png    PBR2DayZ（5 张进 4 张出）
mockup_watermark.png   水印页（嵌入模式）
mockup_smdi.png        SMDI 页
mockup_settings.png    设置页
mockup_empty.png       列表空着的时候
mockup_issues.png      底部"问题"面板展开
mockup_overlay.png     点缩略图弹出大图
```

样张代码：`build/mockup/mockup.py` + `build/mockup/details.py`（**纯样张，不 import 项目任何模块，跟正式代码无关**）

---

## 实施补记（做完之后回头补的，跟计划不一样的地方）

计划是照着"还没动手时看到的代码"写的，真做起来有六处对不上，都按实际情况改了：

1. **Game2PBR 的匹配方式**从开关改成了 `精准 / 模糊` 分段控件，跟 PBR2DayZ 页统一。同一个概念在两个页面用两种控件，正是要避免的毛病。

2. **水印页"变灰"的规则反过来了。** 计划写的是"切到检测时把 内容/长度/覆盖原图 变灰"，但 `detect_watermark` **必须有长度**（长度为 0 直接返回 `Watermark length must be greater than 0.`），照计划做检测永远跑不起来。改成：嵌入模式 → 内容/密码/覆盖原图 可用、长度变灰（长度是跑出来的结果，跑完自动回填）；检测模式 → 密码/长度 可用、内容/覆盖原图 变灰。

3. **Game2PBR 没跑过的行也先把输出槽位摆出来**（灰底 + "—" + 槽位名）。计划里只对 PBR2DayZ 写了"缺的留灰底槽标无"，但两页应该长得一样；而且这样用户在按开始之前就看得见"这一张会出三张"，正是这个界面存在的理由。

4. **PBR2DayZ 的分组行为**：`prefix_mode="auto"`（默认）下前缀取的是**文件夹名**，所以**同一个文件夹里的所有贴图会被归成一组**（每种类型只留第一张）。要一组一组分开，得每个贴图集一个子文件夹，或者把前缀模式改成 `filename_prefix`。这是工具的既有行为（旧界面走同一个函数），不是新界面的改动，但文档里得说清楚，否则第一次用会以为坏了。

5. **翻译原文的语言由默认语言决定。** 计划原本写"中文原文、英文译文"，用户后来把默认语言改成了英文，这就反了 —— 默认界面一旦漏翻会退回中文，正是要消灭的静默漏翻。最终是**英文原文写在代码里，`.ts` 放中文译文**，152 条全译，漏翻只会退回英文。

6. **逻辑层的提示**：一共 30 处写死的英文，其中 5 处是 `f"{type(exc).__name__}: {exc}"` 异常壳不翻，剩 25 处套了 `QCoreApplication.translate`。没装翻译器时原样返回英文，所以 69 个逻辑层测试完全不受影响。

实测数字（跟计划里的估算对一下）：

```
测试        90 个用例全过（69 逻辑层 + 21 界面层）
漏翻体检    没有漏翻的英文
出包体积    269 MB（计划估算 220–280 MB）
pip check   No broken requirements found.
```

新增的验证脚本（都在 `build/`，跟正式代码无关）：

```
build/run_test.py         界面跑一遍 vs 直接调库跑一遍，逐字节比 md5
build/check_language.py   中文界面下扫所有可见文字，找出漏翻的英文
build/live_test.py        造测试贴图 + 给四页塞数据 + 截图
build/detail_test.py      问题面板 / 大图浮层 / 浅色主题截图
build/shot.py             五页截图（LANG_CODE=zh|en 切语言）
build/fill_translation.py 一次性把 .ts 里的中文译文填上
```
