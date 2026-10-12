---
name: DayZ Texture Tool
description: DayZ 贴图转换桌面工具 —— 中性灰外壳，把"一张进、几张出"直接画在列表里
colors:
  shell: "#181818"
  content: "#1e1e1e"
  row-hover: "#242424"
  well: "#2a2a2a"
  well-source: "#313131"
  btn: "#2d2d2d"
  btn-hover: "#383838"
  field: "#232323"
  line: "#2a2a2a"
  line-strong: "#3a3a3a"
  text: "#ececec"
  text-dim: "#b4b4b4"
  text-muted: "#8c8c8c"
  accent: "#29f7ff"
  accent-ink: "#0d1416"
  accent-hover: "#5efaff"
  ok: "#3fb950"
  err: "#f85149"
  skip: "#8c8c8c"
typography:
  page-title:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "11pt"
    fontWeight: 700
  section-title:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "9.5pt"
    fontWeight: 700
  body:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "9pt"
    fontWeight: 400
  small:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "8.5pt"
    fontWeight: 400
  tiny:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "8pt"
    fontWeight: 400
  micro:
    fontFamily: "Microsoft YaHei UI"
    fontSize: "7.5pt"
    fontWeight: 400
rounded:
  control: "4px"
  card: "6px"
  lightbox: "8px"
spacing:
  page-pad: "22px"
  row-pad: "12px"
  row-pad-end: "16px"
  cell-gap: "2px"
  cell: "70px"
  sidebar: "200px"
  nav: "38px"
  row: "112px"
  thumb: "64px"
  control: "30px"
  header: "32px"
  status: "46px"
  progress: "360px"
components:
  nav-item:
    backgroundColor: "{colors.shell}"
    textColor: "{colors.text}"
    typography: "{typography.body}"
    height: "{spacing.nav}"
    width: "{spacing.sidebar}"
  nav-item-active:
    backgroundColor: "{colors.row-hover}"
    textColor: "{colors.accent}"
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.control}"
    height: "{spacing.control}"
  button-primary-disabled:
    backgroundColor: "{colors.btn}"
    textColor: "{colors.text-muted}"
  button:
    backgroundColor: "{colors.btn}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "{spacing.control}"
  button-hover:
    backgroundColor: "{colors.btn-hover}"
  field:
    backgroundColor: "{colors.field}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    height: "{spacing.control}"
  card:
    backgroundColor: "{colors.shell}"
    rounded: "{rounded.card}"
  well:
    backgroundColor: "{colors.well}"
    rounded: "{rounded.control}"
    size: "{spacing.thumb}"
  well-source:
    backgroundColor: "{colors.well-source}"
    rounded: "{rounded.control}"
    size: "{spacing.thumb}"
---

# DayZ Texture Tool · 界面设计契约

## Overview

这是一个**工具**，不是展示品。用的人正在处理一批贴图，他要的是"这 50 张会变成什么、跑完没有、哪几张出问题了"，一眼看完就走。

所以界面的立场是：**外壳安静，把颜色额度全留给贴图本身。** 这个软件是用来判断贴图颜色的，界面自己带颜色会骗眼睛 —— Photoshop、达芬奇在图片周围一律铺中性灰，同一个道理。

一句话概括这个界面独有的东西：**它把"一张进、几张出"直接画出来。** 别的批量工具给你一个文件名列表和一个进度条；这里每一行左边是进来的那张原图，一个箭头，右边扇形展开它将要变成的（或已经变成的）每一张，每张下面带自己的名字和大小。用户不需要记住"DF_NRM 会出三张"，他看得见。

界面分五页，左边一条 200px 的侧边栏切换：Game2PBR、PBR2DayZ、水印、SMDI、设置。打开软件停在上次用的那一页。

## Colors

两套主题都是**中性灰**，一个色相都不带。深浅不是"风格选择"，是使用场景决定的 —— 用户白天在车间、晚上在宿舍都用这个工具，所以设置里给一个开关，两套都是中性灰，浅色不是把深色反过来（`#e6e6e6` 底 + `#1a1a1a` 字，不是负片）。

三层灰构成外壳的纵深：

- `shell #181818` —— 侧边栏和底部状态栏，比内容面暗一档。**导航和状态是"壳"，内容才是"纸"。**
- `content #1e1e1e` —— 列表和设置页的底。
- `btn #2d2d2d` / `well #2a2a2a` —— 抬起来的控件和缩略图的底槽。

**青色 `#29f7ff` 只出现在三个地方，一个都不多：** 当前选中的侧边栏项、右下角的主操作按钮、进度条。它在这三处做同一件事 —— 回答"现在轮到哪了 / 按哪个"。除此之外界面上没有任何彩色，包括标题、链接、图标（图标一律 `text-dim`）。

缩略图的底槽分两档是有意义的：**输入图的底槽 `#313131` 比输出亮一档，还带一圈 1px 边框**，一眼分清哪个是"源头"、哪些是"产物"。

状态色三个，只加在灰底之上携带意义的地方：完成 `ok #3fb950`、失败 `err #f85149`、跳过 `skip #8c8c8c`。跳过用灰不用红是刻意的 —— 拖 50 张进去、47 张跳过，说明后缀配错了，这是**用户自己的配置问题**，标红会让人以为软件坏了。

对比度都过线：`text_muted #8c8c8c` 对 `#1e1e1e` 是 4.97:1，`ok` 6.57:1，`err` 4.97:1。彩色面上的字不用灰，用该色相染过的深色（青底上配 `accent_ink #0d1416`）。

## Typography

一个字体家族，`Microsoft YaHei UI`，扛下全部。产品界面不需要"显示字体 + 正文"配对。

六级固定台阶，**不随窗口缩放**（用户在高分屏上看，会缩的字在侧边栏里更难看）：11pt 页面标题 / 9.5pt 区块标题 / 9pt 正文·按钮·列表 / 8.5pt 次要信息 / 8pt 缩略图名·列表表头 / 7.5pt 文件大小·状态备注。

**加粗只用在标题上。** 界面里所有"强调"要么靠字号、要么靠颜色，不靠字重堆。

## Layout

窗口默认 1440×900，最小 1100×700，大小和位置记住。

左侧 200px 侧边栏（顶部品牌名，四个功能项高 38px，撑开后底部分隔线，然后设置和语言）。右侧内容区从上到下四段：页面标题 → 工具条（高 30px 控件，底下一条 1px 线）→ 列表表头（高 32px）→ 行 → 底部状态栏（高 46px，`shell` 底，左边状态文字，右边百分比 + 360px 进度条 + 主按钮）。

行高 112px，左右边距 12 / 16px。列宽固定：勾选框 30 / 文件名 184 / 变换前 / 箭头 30 / 变换后（吃剩余宽度）/ 1px 竖线 / 尺寸大小 142 / 状态 130。

**"变换前"那一列的宽度是按页固定的**（Game2PBR 70px 单张，PBR2DayZ 358px = 5 张 × 70 + 4 × 2 间距）。这样箭头和"变换后"在整页里 x 坐标恒定，表头也能对齐 —— 用户的眼睛不用每行重新找位置。

尺寸和状态两列前面有一条 `line_strong` 的竖线，把中间那段空当变成一条刻意的分隔，而不是留白。

缩略图统一 70px 宽 = 64×64 的图 + 名字 + 大小三行。名字是必需的：`_Metal` / `_Rou` / `_N` 才是用户真正要读的东西。

## Elevation & Depth

**这个界面几乎没有纵深。** 没有阴影、没有玻璃、没有浮起。层级靠三样东西表达：灰的深浅、字号、留白。

唯一的例外是大图浮层：它铺满整个窗口，先 `fillRect` 一层 180 透明度的黑把底压暗，再在中间放一张 660px 的卡片（`shell` 底 + 1px `line_strong` 边框 + 8px 圆角）。这是整个软件里唯一一处"盖在别的东西上面"。

动效只表达状态变化，150–250ms，不做入场编排 —— 用户是进来干活的，不是来看它加载的。

## Shapes

圆角两档：控件 4px，卡片和浮层 6–8px。就这样，没有别的形状。

缩略图是直角方块（它是"贴图"，不是"卡片"）。空状态的虚线框是 1px 虚线，不是圆角容器。

进度条是 4px 高的圆角细条，空闲时是一条空槽（`well`），不显示 0%。

## Components

**侧边栏项** —— 高 38px，图标 + 文字。选中时左侧 3px 青条 + 稍亮的底 + 青色图标，文字仍是 `text` 色（不整行染青，那太吵）。

**工具条** —— 每页一行，控件高 30px。里面只放**每批文件都可能要改的**东西（处理模式、匹配方式、几个开关）；配一次能用很久的（各种后缀、ImageToPAA 路径）全在设置页。切页时工具条长度基本不变，不隐藏控件 —— 隐藏会让工具条忽长忽短，用户每换一次模式就要重新找东西在哪。不适用的控件**留在原位变灰**。

**主操作按钮** —— 整页只有右下角一个，青底深字，禁用时变灰。工具条里没有主按钮。

**列表行** —— 左边勾选框（只有会跑的行能勾，不匹配的行整行变暗 40%），文件名 + 上级文件夹，输入缩略图，箭头，输出缩略图，尺寸大小，状态。没跑过的行**也把输出槽位摆出来**（灰底 + "—" + 槽位名），让人在按开始之前就看见这一张会出几张；跑完之后槽位被真图填上。

**空状态** —— 一大块虚线框，中间一个向下的箭头图标、"把贴图拖到这里"、支持的格式、"整个文件夹也可以直接拖进来"、两个按钮（添加文件 / 添加文件夹），最下面一行灰字说清楚**当前是什么模式、按什么后缀匹配** —— 这是新用户最容易踩的坑（拖进来一堆全被跳过，不知道为什么）。

**问题面板** —— 列表下方，只在有失败或跳过时才出现。按"失败 / 跳过"分两组，每组一行一个问题（图标 + 文件名 + 原因）。可以折叠。

**状态栏** —— 左边一句话（多少条待处理 / 完成 X 失败 Y 跳过 Z），右边百分比 + 进度条 + 主按钮。

**设置页** —— 整页滚动，三张卡片（通用 / Game2PBR 后缀 / PBR2DayZ 关键词与后缀）。没有保存按钮，改完立刻存，状态栏写"设置已自动保存"。Game2PBR 那张表是 9 行，每行一种处理模式：模式名 + 识别后缀 + 按槽位分开的几个输出后缀框。

## Do's and Don'ts

**要**

- 颜色只给贴图。界面上除了那三处青色和三个状态色，没有别的颜色。
- 每一行的每一张小图都带名字和大小。名字是内容，不是装饰。
- 不适用的控件留原位变灰，不要隐藏。
- 空状态教人怎么用，不是"这里什么都没有"。
- 状态点用颜色 + 文字双重表达，不要只给颜色（色觉差异）。
- 图标来自 qtawesome（Phosphor 一套），统一 18px，统一笔画。

**不要**

- 不要在标题上方加小标签（kicker / eyebrow）。标题自己承重。
- 不要渐变文字、不要装饰性模糊、不要卡片套卡片。
- 不要给"好看"加动画。动效只表达状态变化。
- 不要用 emoji 或 Unicode 符号冒充图标。
- 不要在内容中间转圈。加载用空底槽（骨架）。
- 不要为风味重新发明标准控件（自定义滚动条、怪异的下拉、非标准弹窗）。
- 不要用模态当第一想法。能行内解决就行内解决。
- 不要把等宽字体当"技术感"戏服。
- 不要在同一个概念上给两个页面两种控件（两处的"匹配方式"都得是同一个分段控件）。
