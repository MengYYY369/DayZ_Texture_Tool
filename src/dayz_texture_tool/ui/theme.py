"""调色板、字号台阶、全局样式表。

两套主题都是**中性灰**，不带色相 —— 这个工具是用来判断贴图颜色的，界面自己带颜色
会骗眼睛（跟 Photoshop、达芬奇在图片周围一律用中性灰是同一个道理）。

青色（accent）只用在三处：当前选中的侧边栏项、主操作按钮、进度条。
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

FAMILY = "Microsoft YaHei UI"

# 字号台阶：固定，不随窗口缩放。加粗只用在标题上。
PT_PAGE = 11.0
PT_SECTION = 9.5
PT_BODY = 9.0
PT_SMALL = 8.5
PT_TINY = 8.0
PT_MICRO = 7.5

# 尺寸
SIDEBAR_W = 200
NAV_H = 38
ROW_H = 112
THUMB = 64
THUMB_W = 70
CONTROL_H = 30
HEADER_H = 32
STATUS_H = 46
PROGRESS_W = 360
PAGE_PAD = 22
RADIUS = 4
RADIUS_CARD = 6


@dataclass(frozen=True)
class Theme:
    name: str
    shell: str
    content: str
    row_hover: str
    well: str
    well_in: str
    btn: str
    btn_hover: str
    field: str
    line: str
    line_strong: str
    text: str
    text_dim: str
    text_muted: str
    accent: str
    accent_ink: str
    accent_hover: str
    ok: str
    err: str
    skip: str


DARK = Theme(
    name="dark",
    shell="#181818",
    content="#1e1e1e",
    row_hover="#242424",
    well="#2a2a2a",
    well_in="#313131",
    btn="#2d2d2d",
    btn_hover="#383838",
    field="#232323",
    line="#2a2a2a",
    line_strong="#3a3a3a",
    text="#ececec",
    text_dim="#b4b4b4",
    text_muted="#8c8c8c",  # 对 #1e1e1e 的对比度 4.97:1
    accent="#29f7ff",
    accent_ink="#0d1416",
    accent_hover="#5efaff",
    ok="#3fb950",  # 对 #1e1e1e 6.57:1
    err="#f85149",  # 4.97:1
    skip="#8c8c8c",
)

LIGHT = Theme(
    name="light",
    shell="#e6e6e6",
    content="#f5f5f5",
    row_hover="#ececec",
    well="#e0e0e0",
    well_in="#d5d5d5",
    btn="#eaeaea",
    btn_hover="#dedede",
    field="#ffffff",
    line="#e0e0e0",
    line_strong="#c6c6c6",
    text="#1a1a1a",
    text_dim="#4d4d4d",
    text_muted="#6b6b6b",  # 对 #f5f5f5 的对比度 4.89:1
    accent="#0d7084",  # 5.25:1
    accent_ink="#ffffff",
    accent_hover="#0a5c6d",
    ok="#1a7f37",  # 4.66:1
    err="#cf222e",  # 4.91:1
    skip="#6b6b6b",
)

THEMES = {"dark": DARK, "light": LIGHT}
DEFAULT_THEME = "dark"

_ACTIVE: Theme = DARK


def current() -> Theme:
    """当前主题。控件在构造时读它取颜色。"""
    return _ACTIVE


def stylesheet(t: Theme) -> str:
    """全局样式表。所有控件的外观都从这里来，主题切换 = 换这一张表。"""
    return f"""
/* ---------------------------------------------------------- 基础 */
QWidget {{ color: {t.text}; }}
QWidget#Root, QWidget#Sidebar {{ background: {t.shell}; }}
QWidget#Content, QWidget#Page, QWidget#Body, QWidget#Inner {{ background: {t.content}; }}
QWidget#Toolbar {{ background: {t.content}; border-bottom: 1px solid {t.line}; }}
QWidget#ListHeader {{ background: {t.content}; border-bottom: 1px solid {t.line_strong}; }}
QWidget#StatusBar {{ background: {t.shell}; border-top: 1px solid {t.line}; }}
QWidget#Card {{ background: {t.shell}; border: 1px solid {t.line}; border-radius: {RADIUS_CARD}px; }}
QWidget#CardRow {{ background: transparent; border-top: 1px solid {t.line}; }}
QFrame#Rule {{ background: {t.line_strong}; }}
QFrame#HLine {{ background: {t.line}; }}

/* ---------------------------------------------------------- 文字 */
QLabel#PageTitle {{ font-size: {PT_PAGE}pt; font-weight: bold; padding: 16px 0 10px {PAGE_PAD}px; }}
QLabel#SectionTitle {{ font-size: {PT_SECTION}pt; font-weight: bold; }}
QLabel#Body {{ font-size: {PT_BODY}pt; }}
QLabel#Small {{ font-size: {PT_SMALL}pt; }}
QLabel#Tiny {{ font-size: {PT_TINY}pt; }}
QLabel#Micro {{ font-size: {PT_MICRO}pt; }}
QLabel#Hint {{ font-size: {PT_TINY}pt; color: {t.text_muted}; }}
QLabel#SmallDim {{ font-size: {PT_SMALL}pt; color: {t.text_dim}; }}
QLabel#SmallMuted {{ font-size: {PT_SMALL}pt; color: {t.text_muted}; }}
QLabel#MicroMuted {{ font-size: {PT_MICRO}pt; color: {t.text_muted}; }}
QLabel#TinyMuted {{ font-size: {PT_TINY}pt; color: {t.text_muted}; }}
QLabel#TinyErr {{ font-size: {PT_TINY}pt; color: {t.err}; }}
QLabel#EmptyTitle {{ font-size: 13pt; font-weight: bold; }}
QFrame#EmptyBox {{ border: 1px dashed {t.line_strong}; background: {t.well}; }}
QFrame#ThinRule {{ background: {t.line}; }}
QListView {{ background: {t.content}; border: none; }}
QLabel#Dim {{ color: {t.text_dim}; }}
QLabel#Muted {{ color: {t.text_muted}; }}
QLabel#Ok {{ color: {t.ok}; }}
QLabel#Err {{ color: {t.err}; }}

/* ---------------------------------------------------------- 侧边栏 */
QPushButton#NavItem {{
    background: transparent; color: {t.text_dim};
    font-size: {PT_SECTION}pt; text-align: left;
    padding-left: 13px; border: none;
    border-left: 3px solid transparent;
}}
QPushButton#NavItem:hover {{ background: {t.row_hover}; color: {t.text}; }}
QPushButton#NavItem[active="true"] {{
    background: {t.btn}; color: {t.accent};
    font-weight: bold; border-left: 3px solid {t.accent};
}}
QPushButton#LangButton {{
    background: transparent; color: {t.text_dim};
    font-size: {PT_BODY}pt; text-align: left;
    padding-left: 16px; border: none;
}}
QPushButton#LangButton:hover {{ background: {t.row_hover}; color: {t.text}; }}

/* ---------------------------------------------------------- 按钮 */
QPushButton#Primary {{
    background: {t.accent}; color: {t.accent_ink};
    font-size: {PT_BODY}pt; font-weight: bold;
    padding: 0 18px; border: none; border-radius: {RADIUS}px;
}}
QPushButton#Primary:hover {{ background: {t.accent_hover}; }}
QPushButton#Primary:disabled {{ background: {t.btn}; color: {t.text_muted}; }}
QPushButton#Btn {{
    background: {t.btn}; color: {t.text};
    font-size: {PT_BODY}pt; padding: 0 16px;
    border: 1px solid {t.line_strong}; border-radius: {RADIUS}px;
}}
QPushButton#Btn:hover {{ background: {t.btn_hover}; }}
QPushButton#Btn:disabled {{ color: {t.text_muted}; }}
QPushButton#Ghost {{
    background: transparent; color: {t.text_dim};
    font-size: {PT_BODY}pt; padding: 0 10px; border: none;
}}
QPushButton#Ghost:hover {{ background: {t.btn_hover}; color: {t.text}; }}
QPushButton#MenuBtn {{
    background: transparent; color: {t.text_dim};
    font-size: {PT_BODY}pt; padding-left: 10px; padding-right: 26px; border: none;
}}
QPushButton#MenuBtn:hover {{ background: {t.btn_hover}; color: {t.text}; }}
QPushButton#MenuBtn::menu-indicator {{ image: none; width: 0px; height: 0px; }}
QPushButton#Toggle {{
    background: transparent; color: {t.text_dim};
    font-size: {PT_BODY}pt; padding: 0 10px;
    border: 1px solid {t.line_strong}; border-radius: {RADIUS}px;
}}
QPushButton#Toggle:hover {{ background: {t.btn_hover}; color: {t.text}; }}
QPushButton#Toggle[on="true"] {{ color: {t.text}; }}
QPushButton#Toggle:disabled {{ color: {t.text_muted}; border-color: {t.line}; }}
QComboBox#Combo {{
    background: {t.btn}; color: {t.text};
    font-size: {PT_BODY}pt;
    padding-left: 10px; padding-right: 26px;
    border: 1px solid {t.line_strong}; border-radius: {RADIUS}px;
}}
QComboBox#Combo:hover {{ background: {t.btn_hover}; }}
QComboBox#Combo:disabled {{ color: {t.text_muted}; border-color: {t.line}; }}
QComboBox#Combo::drop-down {{ border: none; width: 0px; }}
QComboBox#Combo::down-arrow {{ image: none; width: 0px; height: 0px; }}
QComboBox QAbstractItemView {{
    background: {t.btn}; color: {t.text};
    border: 1px solid {t.line_strong};
    selection-background-color: {t.btn_hover}; selection-color: {t.text};
    outline: none;
}}

/* ---------------------------------------------------------- 分段控件 */
QWidget#Seg {{ background: {t.field}; border: 1px solid {t.line_strong}; border-radius: {RADIUS}px; }}
QPushButton#SegBtn {{
    background: transparent; color: {t.text_muted};
    font-size: {PT_BODY}pt; padding: 0 12px;
    border: none; border-radius: 3px;
}}
QPushButton#SegBtn:checked {{ background: {t.btn_hover}; color: {t.text}; font-weight: bold; }}
QPushButton#SegBtn:disabled {{ color: {t.line_strong}; }}

/* ---------------------------------------------------------- 输入 */
QLineEdit#Field {{
    background: {t.field}; color: {t.text};
    font-size: {PT_SMALL}pt; padding-left: 8px;
    border: 1px solid {t.line_strong}; border-radius: {RADIUS}px;
}}
QLineEdit#Field:focus {{ border: 1px solid {t.accent}; }}
QLineEdit#Field:disabled {{ color: {t.text_muted}; border-color: {t.line}; }}
QLineEdit#Field[invalid="true"] {{ border: 1px solid {t.err}; }}
QLineEdit#Field::placeholder {{ color: {t.text_muted}; }}

/* ---------------------------------------------------------- 列表 */
QWidget#Row {{ background: {t.content}; border-bottom: 1px solid {t.line}; }}
QWidget#Row:hover {{ background: {t.row_hover}; }}
QWidget#Well {{ background: {t.well}; }}
QWidget#Well[source="true"] {{ background: {t.well_in}; border: 1px solid {t.line_strong}; }}
QWidget#Arrow {{ background: transparent; }}

/* ---------------------------------------------------------- 问题面板 */
QWidget#Issues {{ background: {t.shell}; border-top: 1px solid {t.line_strong}; }}
QPushButton#IssuesToggle {{
    background: transparent; color: {t.text_dim};
    font-size: {PT_SMALL}pt; padding: 0 8px; border: none;
}}
QPushButton#IssuesToggle:hover {{ color: {t.text}; }}

/* ---------------------------------------------------------- 浮层 */
QWidget#LightboxCard {{
    background: {t.shell}; border: 1px solid {t.line_strong}; border-radius: 8px;
}}
QLabel#LightboxImage {{ background: {t.well}; border-radius: {RADIUS_CARD}px; }}
QPushButton#StripThumb {{ background: transparent; border: none; }}
QPushButton#IconButton {{
    background: transparent; border: none; border-radius: {RADIUS}px; padding: 4px;
}}
QPushButton#IconButton:hover {{ background: {t.btn_hover}; }}

/* ---------------------------------------------------------- 滚动条 */
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {t.line_strong}; border-radius: 6px; min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{ background: {t.text_muted}; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
QScrollBar::handle:horizontal {{
    background: {t.line_strong}; border-radius: 6px; min-width: 28px;
}}
QScrollBar::handle:horizontal:hover {{ background: {t.text_muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollArea {{ border: none; background: {t.content}; }}
QAbstractScrollArea::corner {{ background: {t.content}; }}

/* ---------------------------------------------------------- 提示 */
QToolTip {{
    background: {t.btn}; color: {t.text_dim};
    border: 1px solid {t.line_strong}; padding: 4px 6px;
}}

/* ---------------------------------------------------------- 菜单 */
QMenu {{
    background: {t.btn}; color: {t.text};
    border: 1px solid {t.line_strong}; padding: 4px;
}}
QMenu::item {{ padding: 5px 14px; border-radius: 3px; }}
QMenu::item:selected {{ background: {t.btn_hover}; }}
QMenu::item:disabled {{ color: {t.text_muted}; }}
QMenu::separator {{ height: 1px; background: {t.line}; margin: 4px 6px; }}
"""


def qpalette(t: Theme) -> QPalette:
    """给 Qt 自带控件（菜单、下拉列表、文件对话框）兜底。"""
    p = QPalette()
    p.setColor(QPalette.Window, QColor(t.content))
    p.setColor(QPalette.WindowText, QColor(t.text))
    p.setColor(QPalette.Base, QColor(t.field))
    p.setColor(QPalette.AlternateBase, QColor(t.content))
    p.setColor(QPalette.Text, QColor(t.text))
    p.setColor(QPalette.Button, QColor(t.btn))
    p.setColor(QPalette.ButtonText, QColor(t.text))
    p.setColor(QPalette.Highlight, QColor(t.accent))
    p.setColor(QPalette.HighlightedText, QColor(t.accent_ink))
    p.setColor(QPalette.ToolTipBase, QColor(t.btn))
    p.setColor(QPalette.ToolTipText, QColor(t.text_dim))
    p.setColor(QPalette.PlaceholderText, QColor(t.text_muted))
    p.setColor(QPalette.Link, QColor(t.accent))
    for role in (QPalette.Text, QPalette.WindowText, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(t.text_muted))
    return p


def apply(app: QApplication, name: str) -> Theme:
    """套用主题。换主题只需要再调一次。"""
    global _ACTIVE
    t = THEMES.get(name, DARK)
    _ACTIVE = t
    app.setStyle("Fusion")
    app.setPalette(qpalette(t))
    app.setStyleSheet(stylesheet(t))
    return t
