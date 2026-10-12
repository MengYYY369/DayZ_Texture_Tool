# -*- mode: python ; coding: utf-8 -*-
"""打包配置。

体积是这份文件最费心的地方，所以每条过滤都写清楚它砍掉什么、为什么安全。
要改的话，改完必须出包双击跑一遍，五个页面都点过。
"""
from PyInstaller.building.datastruct import TOC
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = []
# qtawesome 的字体和 PySide6 的库文件都有现成的 hook，不用手动 collect_all
tmp_ret = collect_all('blind_watermark')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

# 中文翻译。shell.py 是按 __file__ 旁边找这个目录的
datas += [
    ('src\\dayz_texture_tool\\ui\\translations\\dayz_zh_CN.qm', 'dayz_texture_tool\\ui\\translations'),
]

# --------------------------------------------------------------- 体积过滤
# 界面只用 QtCore / QtGui / QtWidgets 三个模块（全项目就这三条 import 语句），
# 其余 Qt 库都是 hook 顺带扫进来的。整个目录里没有一处引用 Qt6OpenGL，
# 所以 OpenGL 那一套也能整个拿掉。
QT_KEEP = {
    "Qt6Core.dll", "Qt6Gui.dll", "Qt6Widgets.dll",
    "QtCore.pyd", "QtGui.pyd", "QtWidgets.pyd",
}

# 按文件名匹配，整个不要的二进制
DROP_BINARIES = (
    "opencv_videoio_ffmpeg",  # 视频编解码库，这个工具只处理静态图片
    "opengl32sw",             # 软件 OpenGL 兜底，界面是纯控件，不用 OpenGL
    # 下面两条是构建机 PATH 上 Git 自带的 OpenSSL，跟本程序无关，
    # PyInstaller 扫依赖时顺手抓进来的，不能发出去
    "libssl-3-x64",
    "libcrypto-3-x64",
    "_avif",                  # Pillow 的 AVIF 解码器，支持格式里没有 avif
    "_imagingtk",             # Pillow 给 Tkinter 用的桥，Tkinter 已经删了
    "_webp",                  # 同上，支持格式里没有 webp
)
# Qt 插件里用不到的几类
DROP_PLUGINS = ("sqldrivers", "tls", "networkinformation", "iconengines", "generic")
# 单个插件：svg 要额外的 Qt6Svg（已拿掉）；icns 是 macOS 图标；direct2d 是实验性平台插件；
# webp 不在支持的格式里
DROP_PLUGIN_FILES = ("qsvg.dll", "qicns.dll", "qdirect2d.dll", "qwebp.dll")
# Qt 自带翻译只留中文；英文是原文，不需要翻译文件
QT_TRANSLATIONS = ("qt_zh_CN.qm", "qtbase_zh_CN.qm")


def keep(dest: str) -> bool:
    path = dest.replace("\\", "/")
    name = path.rsplit("/", 1)[-1]

    if any(marker in name for marker in DROP_BINARIES):
        return False

    if "PySide6/plugins/" in path:
        if any(f"/{part}/" in path for part in DROP_PLUGINS):
            return False
        if name in DROP_PLUGIN_FILES:
            return False

    if "PySide6/translations/" in path:
        return name.endswith(QT_TRANSLATIONS)

    # 注意：qtawesome 的字体一套都不能删。它初始化时会把每套字体的 ttf
    # 读出来算 MD5 校验，少一个就 FileNotFoundError，整个程序起不来。

    if name.startswith("Qt6") or (name.startswith("Qt") and name.endswith(".pyd")):
        return name in QT_KEEP

    return True


a = Analysis(
    ['src\\dayz_texture_tool\\app.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 旧的 Tk 界面已经删了，别让 hook 再把它们拖进来
        'tkinter', 'customtkinter', 'tkinterdnd2',
        # 这个工具只读本地文件，没有任何网络行为
        'ssl', '_ssl', 'http', 'urllib.request', 'ftplib', 'smtplib',
        # 开发时才用的
        'unittest', 'doctest', 'pdb', 'pydoc', 'test',
    ],
    noarchive=False,
    optimize=0,
)

# hook 收集完之后再过滤一遍 —— 过滤的是最终落盘的路径，最直接
a.binaries = TOC([entry for entry in a.binaries if keep(entry[0])])
a.datas = TOC([entry for entry in a.datas if keep(entry[0])])

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DayZ_Texture_Tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DayZ_Texture_Tool',
)
