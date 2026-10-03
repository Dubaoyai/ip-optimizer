"""主题系统（深色 / 浅色 / 跟随系统）—— 全项目唯一的配色与样式真源。

设计基准：深色主题参照本机《API总代理》的视觉语言 1:1 复刻 ——
左侧边栏 + 顶栏 + 统计卡片行 + 圆角面板，近黑底 + 紫色强调色。

约定：
1. 所有颜色**只在本文件定义**，界面代码禁止再写字面量十六进制色值；
2. 切换主题只需调 `apply_theme(app, mode)`，界面无需重建 —— 会刷新全局 QSS，
   并通过 `theme.on_changed(callback)` 注册的回调让表格等控件重绘单元格颜色；
3. 深浅两套色板**键名完全一致**，只换值；缺失键回退到深色值，避免 KeyError。

三种模式：
    "dark"   —— 深色（默认）
    "light"  —— 浅色
    "system" —— 跟随系统（读 Windows 的 AppsUseLightTheme 注册表项）
"""

from __future__ import annotations

import sys
from typing import Callable, Dict, List

from PySide6.QtGui import QColor, QFont

# ======================================================================
# 一、色板
# ======================================================================

# ---- 深色主题（默认；数值取自《API总代理》CSS 变量，逐项对应） ----
DARK: Dict[str, str] = {
    # 背景层级：越靠上层的元素越亮，形成纵深
    "BG_PRIMARY": "#0b0b0b",       # 最底层：窗口背景
    "BG_SECONDARY": "#111111",
    "BG_CARD": "#181818",          # 卡片 / 面板底
    "BG_CARD_HOVER": "#202020",
    "BG_INPUT": "#1e1e1e",         # 输入框 / 下拉框底
    "BG_SIDEBAR": "#0e0e0e",
    "BG_ELEVATED": "#232323",      # 悬浮层（表头 / 按钮）
    "BG_ROW_ALT": "#1c1c1c",       # 表格斑马纹
    "BG_SELECT": "#2a2640",        # 表格选中行
    "BG_BUTTON_HOVER": "#2c2c2c",
    "BG_BUTTON_PRESSED": "#161616",
    "BG_DISABLED": "#161616",
    "BG_INPUT_DISABLED": "#141414",

    # 描边
    "BORDER": "#282828",
    "BORDER_LIGHT": "#3a3a3a",

    # 文字
    "TEXT_PRIMARY": "#f5f5f5",
    "TEXT_SECONDARY": "#b0b0b0",
    "TEXT_MUTED": "#6a6a6a",
    "TEXT_DISABLED": "#4a4a4a",
    "TEXT_ON_ACCENT": "#ffffff",

    # 强调色（紫）
    "ACCENT": "#7c6cf0",
    "ACCENT_HOVER": "#9a8cf5",
    "ACCENT_PRESSED": "#5b4ad0",
    "ACCENT_DISABLED_BG": "#2a2640",
    "ACCENT_DISABLED_TEXT": "#6b6580",

    # 状态色
    "GREEN": "#00d4aa",
    "ORANGE": "#ffa502",
    "RED": "#ff4757",
    "BLUE": "#4ea1ff",

    # 状态按钮（危险按钮）
    "DANGER_HOVER": "#ff6272",
    "DANGER_PRESSED": "#d93a49",
    "DANGER_DISABLED_BG": "#3a2026",
    "DANGER_DISABLED_TEXT": "#7a5560",

    # 图标水印（rgba，QsS 不支持 opacity，用半透明色代替）
    "WATERMARK": "rgba(245, 245, 245, 30)",
    # 侧边栏品牌图标渐变的两端（Qt QSS 不支持渐变，取主色固色）
    "BRAND_BG": "#7c6cf0",
    "BRAND_TEXT": "#ffffff",
}

# ---- 浅色主题：键名与深色**完全一致**，只换值 ----
LIGHT: Dict[str, str] = {
    # 背景层级：浅色下越靠上层的元素越"白"，用极浅灰做纵深
    "BG_PRIMARY": "#f7f8fa",
    "BG_SECONDARY": "#f2f3f5",
    "BG_CARD": "#ffffff",
    "BG_CARD_HOVER": "#fafbfc",
    "BG_INPUT": "#ffffff",
    "BG_SIDEBAR": "#f2f3f5",
    "BG_ELEVATED": "#ffffff",
    "BG_ROW_ALT": "#fafbfc",
    "BG_SELECT": "#ece9fd",
    "BG_BUTTON_HOVER": "#f0f1f3",
    "BG_BUTTON_PRESSED": "#e6e8eb",
    "BG_DISABLED": "#eff0f2",
    "BG_INPUT_DISABLED": "#f5f6f7",

    # 描边
    "BORDER": "#e3e5e9",
    "BORDER_LIGHT": "#cfd3da",

    # 文字
    "TEXT_PRIMARY": "#1f2329",
    "TEXT_SECONDARY": "#5a6069",
    "TEXT_MUTED": "#8b9198",
    "TEXT_DISABLED": "#b8bdc4",
    "TEXT_ON_ACCENT": "#ffffff",

    # 强调色：浅色下紫调稍深，保证白底上的对比度
    "ACCENT": "#6b5ae0",
    "ACCENT_HOVER": "#7d6ee8",
    "ACCENT_PRESSED": "#5a49c7",
    "ACCENT_DISABLED_BG": "#e6e3fb",
    "ACCENT_DISABLED_TEXT": "#a9a2d6",

    # 状态色：浅色下加深，避免在白底上看不清
    "GREEN": "#0d9f7f",
    "ORANGE": "#d98600",
    "RED": "#e03131",
    "BLUE": "#1a73e8",

    # 状态按钮（危险按钮）
    "DANGER_HOVER": "#f05252",
    "DANGER_PRESSED": "#c92a2a",
    "DANGER_DISABLED_BG": "#fbe3e3",
    "DANGER_DISABLED_TEXT": "#d9a0a0",

    # 图标水印
    "WATERMARK": "rgba(31, 35, 41, 26)",
    "BRAND_BG": "#6b5ae0",
    "BRAND_TEXT": "#ffffff",
}

# ======================================================================
# 二、尺寸与字体（深浅主题共用）
# ======================================================================

RADIUS = 14                 # 大圆角（卡片 / 面板）
RADIUS_SM = 8               # 小圆角（按钮 / 输入框）
SIDEBAR_WIDTH = 240         # 侧边栏宽 —— .sidebar width: 240px
BRAND_ICON = 56             # 品牌图标边长
BRAND_RADIUS = 14           # 品牌图标圆角
PAD_H = 22                  # 面板横向内边距
PAD_V = 18                  # 面板纵向内边距
CARD_PAD_H = 18             # 统计卡片横向内边距
CARD_PAD_V = 14             # 统计卡片纵向内边距
GAP = 12                    # 栅格间距
GAP_CARD = 20               # 卡片之间的纵向间距
MAIN_PAD_H = 28             # 主内容区横向内边距
MAIN_PAD_V = 20             # 主内容区纵向内边距
HEADER_GAP = 14             # 面板头与内容的下间距
TOPBAR_GAP = 20             # 顶栏与下方内容的下间距
TOPBAR_H = 64               # 顶栏高度

FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'
FONT_MONO = '"Cascadia Mono", "Consolas", monospace'

# ======================================================================
# 三、运行时状态
# ======================================================================

MODES = ("dark", "light", "system")
MODE_LABELS = {"dark": "深色", "light": "浅色", "system": "跟随系统"}
DEFAULT_MODE = "dark"

_current_mode: str = DEFAULT_MODE
_palette: Dict[str, str] = dict(DARK)
_listeners: List[Callable[[], None]] = []


def _detect_system_mode() -> str:
    """检测操作系统当前是深色还是浅色。

    Windows：读注册表 `HKCU\\...\\Themes\\Personalize\\AppsUseLightTheme`
    （1 = 浅色，0 = 深色）。其他平台或读取失败时回退深色。

    Returns:
        "dark" 或 "light"。
    """
    if sys.platform != "win32":
        return "dark"
    try:
        import winreg  # 仅 Windows 可用

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        try:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        finally:
            winreg.CloseKey(key)
        return "light" if int(value) == 1 else "dark"
    except Exception:
        # 读不到注册表（权限/键不存在）时按深色处理，不让程序出错
        return "dark"


def resolve_mode(mode: str) -> str:
    """把用户选择的模式解析为实际生效的主题。

    Args:
        mode: "dark" / "light" / "system" / "auto"。

    Returns:
        实际生效的 "dark" 或 "light"。
    """
    if mode == "system" or mode == "auto":
        return _detect_system_mode()
    return mode if mode in ("dark", "light") else DEFAULT_MODE


def palette() -> Dict[str, str]:
    """返回当前生效的色板字典（只读用途）。"""
    return _palette


def color(key: str) -> str:
    """按键名取当前主题的颜色值。

    Args:
        key: 色板键名（如 "BG_CARD"）。

    Returns:
        颜色字符串；键不存在时回退到深色主题的同名值，仍不存在则返回主文字色。
    """
    if key in _palette:
        return _palette[key]
    return DARK.get(key, DARK["TEXT_PRIMARY"])


def qcolor(key: str) -> QColor:
    """按键名取当前主题颜色的 QColor 对象（供表格等需要 QColor 的场合）。

    Args:
        key: 色板键名。

    Returns:
        对应的 QColor。
    """
    return QColor(color(key))


def current_mode() -> str:
    """返回用户选择的主题模式（dark / light / system）。"""
    return _current_mode


def base_font(size: int = 10, bold: bool = False) -> QFont:
    """构造主题基准字体（统一字体族，避免各控件字体不一致）。

    Args:
        size: 字号（磅）。
        bold: 是否加粗。

    Returns:
        配置好的 QFont。
    """
    font = QFont()
    font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"])
    font.setPointSize(size)
    font.setBold(bold)
    return font


def on_changed(callback: Callable[[], None]) -> None:
    """注册主题变更回调（控件需要按新色值重绘时使用）。

    Args:
        callback: 主题切换后调用的无参函数。
    """
    if callback not in _listeners:
        _listeners.append(callback)


# ======================================================================
# 四、主题偏好持久化（记住用户选择，重启后沿用）
# ======================================================================

_PREFS_FILE_NAME = "ui_prefs.json"


def _prefs_path():
    """返回偏好文件路径（放在可写的数据根目录下）。

    Returns:
        偏好文件的 Path；无法解析数据目录时返回 None。
    """
    try:
        from utils.paths import data_root

        return data_root() / _PREFS_FILE_NAME
    except Exception:
        return None


def load_saved_mode() -> str:
    """读取启动时应使用的主题模式。

    **默认行为 = 深色**（产品要求：每次打开都以深色启动，不受上次切换影响）。

    语义分三种（按优先级）：
    1. 环境变量 `IPO_FORCE_DARK=1` → 强制深色；
    2. 环境变量 `IPO_THEME=<mode>`   → 使用该模式（供测试/高级用户）；
    3. 其余情况                       → **一律返回 DEFAULT_MODE（深色）**。

    说明：早期版本会让用户上次的选择「粘住」并跨启动保留，导致
    「我明明设了默认深色，打开却是浅色」。现改为**不记忆**，
    保证每次启动都是深色 —— 用户在会话内的切换仍即时生效，只是不写盘。

    Returns:
        "dark" / "light" / "system"（默认 "dark"）。
    """
    import os

    if os.environ.get("IPO_FORCE_DARK", "").strip() not in ("", "0", "false", "False"):
        return "dark"

    forced = os.environ.get("IPO_THEME", "").strip()
    if forced in MODES:
        return forced

    # 不读取历史偏好 —— 保证默认深色
    return DEFAULT_MODE


def save_mode(mode: str) -> None:
    """保存主题模式到偏好文件（失败不抛异常，不影响使用）。

    注意：当前版本**不再用保存值做启动恢复**（启动恒为深色），
    本函数仅用于记录用户当次选择，便于排查问题。

    Args:
        mode: 要保存的模式。
    """
    path = _prefs_path()
    if path is None:
        return
    try:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        # 保留文件中可能存在的其他偏好项
        data = {}
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        data["theme_mode"] = mode
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        # 写盘失败（只读目录等）不应阻断主题切换
        pass


def discard_legacy_preference(logger=None) -> None:
    """作废历史遗留的主题偏好（一次性清理）。

    **背景**：旧版本会把用户当次切换的主题写盘并在下次启动沿用。
    若用户曾切到浅色，之后重新打开就会是浅色 —— 与「默认深色」的
    产品要求冲突。此函数在启动时把该记录作废，确保首次升级后即恢复深色。

    做法：把 theme_mode 写回 "dark"（保留文件与其他偏好项，不删文件）。

    Args:
        logger: 可选的 logger，用于记录清理动作。
    """
    path = _prefs_path()
    if path is None or not path.exists():
        return
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("theme_mode") not in (None, "dark"):
            data["theme_mode"] = "dark"
            path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if logger is not None:
                logger.info("已作废旧的主题偏好记录，恢复为深色")
    except Exception:
        # 清理失败不应影响启动
        if logger is not None:
            logger.warning("作废旧主题偏好失败（不影响使用）")


# ======================================================================
# 五、状态色（表格单元格上色用；随主题切换而更新）
# ======================================================================

# 这些会被 refresh_colors() 就地更新，故用模块级变量而非常量
COLOR_SUCCESS: QColor = QColor(DARK["GREEN"])
COLOR_WARNING: QColor = QColor(DARK["ORANGE"])
COLOR_FAILED: QColor = QColor(DARK["RED"])
COLOR_MUTED: QColor = QColor(DARK["TEXT_MUTED"])
COLOR_PRIMARY: QColor = QColor(DARK["TEXT_PRIMARY"])
COLOR_ACCENT: QColor = QColor(DARK["ACCENT"])


def refresh_colors() -> None:
    """按当前色板刷新模块级 QColor 常量（切换主题后必须调用）。"""
    global COLOR_SUCCESS, COLOR_WARNING, COLOR_FAILED
    global COLOR_MUTED, COLOR_PRIMARY, COLOR_ACCENT
    COLOR_SUCCESS = QColor(color("GREEN"))
    COLOR_WARNING = QColor(color("ORANGE"))
    COLOR_FAILED = QColor(color("RED"))
    COLOR_MUTED = QColor(color("TEXT_MUTED"))
    COLOR_PRIMARY = QColor(color("TEXT_PRIMARY"))
    COLOR_ACCENT = QColor(color("ACCENT"))


# ======================================================================
# 六、QSS 样式表（按当前色板生成）
# ======================================================================

def build_qss() -> str:
    """按当前色板生成完整 QSS 样式表。

    Returns:
        可直接交给 QApplication.setStyleSheet 的样式表字符串。
    """
    c = color  # 简写，便于下方 f-string 内取色
    return f"""
/* ============ 全局基础 ============ */
/* 注意：只给顶层窗口与容器设底色，不给裸 QWidget 设 background-color——
   否则卡片内部的 QLabel 等子控件会各带一块不透明底色，形成突兀色块。 */
QMainWindow, QDialog {{
    background-color: {c('BG_PRIMARY')};
    color: {c('TEXT_PRIMARY')};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QWidget {{
    color: {c('TEXT_PRIMARY')};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QLabel {{
    background: transparent;
    color: {c('TEXT_PRIMARY')};
}}
QToolTip {{
    background-color: {c('BG_ELEVATED')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER_LIGHT')};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ============ 滚动条 ============ */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c('BORDER_LIGHT')};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {c('ACCENT')};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c('BORDER_LIGHT')};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {c('ACCENT')};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0; width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

/* ============ 滚动区 ============ */
QScrollArea {{
    border: none;
    background-color: {c('BG_PRIMARY')};
}}
QScrollArea > QWidget > QWidget {{
    background-color: {c('BG_PRIMARY')};
}}
QWidget#PageContainer {{
    background-color: transparent;
}}

/* ============ 侧边栏 ============ */
QWidget#Sidebar {{
    background-color: {c('BG_SIDEBAR')};
    border-right: 1px solid {c('BORDER')};
}}
QWidget#SidebarBrand {{
    background-color: transparent;
}}
#BrandTitle {{
    color: {c('TEXT_PRIMARY')};
    font-size: 19px;
    font-weight: bold;
    background: transparent;
}}
#BrandSub {{
    color: {c('TEXT_MUTED')};
    font-size: 11px;
    font-weight: 500;
    background: transparent;
}}
#BrandIcon {{
    background-color: {c('BRAND_BG')};
    color: {c('BRAND_TEXT')};
    border-radius: {BRAND_RADIUS}px;
    font-size: 17px;
    font-weight: bold;
}}
#SidebarSection {{
    color: {c('TEXT_MUTED')};
    font-size: 11px;
    padding: 10px 4px 4px 4px;
    background: transparent;
}}
QPushButton#NavButton {{
    background-color: transparent;
    color: {c('TEXT_SECONDARY')};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#NavButton:hover {{
    background-color: {c('BG_CARD')};
    color: {c('TEXT_PRIMARY')};
}}
QPushButton#NavButton:checked {{
    background-color: {c('BG_CARD')};
    color: {c('TEXT_PRIMARY')};
    border-left: 3px solid {c('ACCENT')};
    font-weight: bold;
}}

/* ============ 顶栏 ============ */
QWidget#TopBar {{
    background-color: {c('BG_PRIMARY')};
    border-bottom: 1px solid {c('BORDER')};
}}
#PageTitle {{
    color: {c('TEXT_PRIMARY')};
    font-size: 20px;
    font-weight: bold;
    background: transparent;
}}
#PageSubtitle {{
    color: {c('TEXT_MUTED')};
    font-size: 13px;
    background: transparent;
}}

/* ============ 卡片 / 面板 ============ */
QWidget#Card {{
    background-color: {c('BG_CARD')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS}px;
}}
QWidget#StatCard {{
    background-color: {c('BG_CARD')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS}px;
}}
QWidget#StatCard:hover {{
    background-color: {c('BG_CARD_HOVER')};
    border: 1px solid {c('BORDER_LIGHT')};
}}
QWidget#PanelHeader {{
    background-color: transparent;
    border: none;
}}
QFrame#PanelDivider {{
    background-color: {c('BORDER')};
    border: none;
    max-height: 1px;
}}
#StatLabel {{
    color: {c('TEXT_MUTED')};
    font-size: 11px;
    font-weight: 500;
    background: transparent;
}}
#StatValue {{
    color: {c('TEXT_PRIMARY')};
    font-size: 26px;
    font-weight: bold;
    background: transparent;
}}
#StatUnit {{
    color: {c('TEXT_MUTED')};
    font-size: 12px;
    background: transparent;
}}
#PanelTitle {{
    color: {c('TEXT_PRIMARY')};
    font-size: 16px;
    font-weight: bold;
    background: transparent;
}}

/* ============ 文字层级 ============ */
#Muted {{
    color: {c('TEXT_MUTED')};
    font-size: 12px;
    background: transparent;
}}
#Secondary {{
    color: {c('TEXT_SECONDARY')};
    font-size: 12px;
    background: transparent;
}}
#Hint {{
    color: {c('TEXT_MUTED')};
    font-size: 12px;
    background: transparent;
}}
#Success {{
    color: {c('GREEN')};
    font-size: 12px;
    background: transparent;
}}
#Warning {{
    color: {c('ORANGE')};
    font-size: 12px;
    background: transparent;
}}
#Danger {{
    color: {c('RED')};
    font-size: 12px;
    background: transparent;
}}

/* ============ 按钮 ============ */
QPushButton {{
    background-color: {c('BG_ELEVATED')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER_LIGHT')};
    border-radius: {RADIUS_SM}px;
    padding: 7px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: {c('BG_BUTTON_HOVER')};
    border-color: {c('ACCENT')};
}}
QPushButton:pressed {{
    background-color: {c('BG_BUTTON_PRESSED')};
}}
QPushButton:disabled {{
    background-color: {c('BG_DISABLED')};
    color: {c('TEXT_DISABLED')};
    border-color: {c('BORDER')};
}}

QPushButton#PrimaryButton {{
    background-color: {c('ACCENT')};
    color: {c('TEXT_ON_ACCENT')};
    border: 1px solid {c('ACCENT')};
    font-weight: bold;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {c('ACCENT_HOVER')};
    border-color: {c('ACCENT_HOVER')};
}}
QPushButton#PrimaryButton:pressed {{
    background-color: {c('ACCENT_PRESSED')};
}}
QPushButton#PrimaryButton:disabled {{
    background-color: {c('ACCENT_DISABLED_BG')};
    color: {c('ACCENT_DISABLED_TEXT')};
    border-color: {c('ACCENT_DISABLED_BG')};
}}

QPushButton#DangerButton {{
    background-color: {c('RED')};
    color: #ffffff;
    border: 1px solid {c('RED')};
    font-weight: bold;
}}
QPushButton#DangerButton:hover {{
    background-color: {c('DANGER_HOVER')};
    border-color: {c('DANGER_HOVER')};
}}
QPushButton#DangerButton:pressed {{
    background-color: {c('DANGER_PRESSED')};
}}
QPushButton#DangerButton:disabled {{
    background-color: {c('DANGER_DISABLED_BG')};
    color: {c('DANGER_DISABLED_TEXT')};
    border-color: {c('DANGER_DISABLED_BG')};
}}

QPushButton#GhostButton {{
    background-color: transparent;
    color: {c('TEXT_SECONDARY')};
    border: 1px solid {c('BORDER_LIGHT')};
}}
QPushButton#GhostButton:hover {{
    background-color: {c('BG_CARD_HOVER')};
    color: {c('TEXT_PRIMARY')};
    border-color: {c('ACCENT')};
}}

/* ============ 输入控件 ============ */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {c('BG_INPUT')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS_SM}px;
    padding: 7px 10px;
    selection-background-color: {c('ACCENT')};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {c('ACCENT')};
}}
QLineEdit:disabled, QPlainTextEdit:disabled {{
    background-color: {c('BG_INPUT_DISABLED')};
    color: {c('TEXT_DISABLED')};
}}
QLineEdit[readOnly="true"] {{
    background-color: {c('BG_INPUT_DISABLED')};
    color: {c('TEXT_SECONDARY')};
}}

QSpinBox {{
    background-color: {c('BG_INPUT')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS_SM}px;
    padding: 6px 8px;
    min-width: 60px;
}}
QSpinBox:focus {{
    border: 1px solid {c('ACCENT')};
}}
QSpinBox:disabled {{
    background-color: {c('BG_INPUT_DISABLED')};
    color: {c('TEXT_DISABLED')};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0;
    border: none;
}}

QComboBox {{
    background-color: {c('BG_INPUT')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
    min-width: 70px;
}}
QComboBox:hover {{
    border-color: {c('BORDER_LIGHT')};
}}
QComboBox:focus, QComboBox:on {{
    border: 1px solid {c('ACCENT')};
}}
QComboBox:disabled {{
    background-color: {c('BG_INPUT_DISABLED')};
    color: {c('TEXT_DISABLED')};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {c('TEXT_SECONDARY')};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c('BG_ELEVATED')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER_LIGHT')};
    border-radius: {RADIUS_SM}px;
    padding: 4px;
    outline: none;
    selection-background-color: {c('ACCENT')};
    selection-color: #ffffff;
}}

/* ============ 复选框 / 单选框 ============ */
QCheckBox, QRadioButton {{
    color: {c('TEXT_PRIMARY')};
    spacing: 8px;
    background: transparent;
    padding: 3px 0;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: {c('TEXT_DISABLED')};
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {c('BORDER_LIGHT')};
    background-color: {c('BG_INPUT')};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {c('ACCENT')};
}}
/* 勾选态：实心强调色 + 白色对勾（用 border 技巧画对勾，避免依赖图片资源） */
QCheckBox::indicator:checked {{
    background-color: {c('ACCENT')};
    border: 2px solid {c('ACCENT')};
    image: none;
}}
QRadioButton::indicator:checked {{
    background-color: {c('ACCENT')};
    border: 4px solid {c('BG_INPUT')};
    outline: 1px solid {c('ACCENT')};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {c('BG_DISABLED')};
    border-color: {c('BORDER')};
}}

/* ============ 进度条 ============ */
QProgressBar {{
    background-color: {c('BG_INPUT')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS_SM}px;
    height: 20px;
    text-align: center;
    color: {c('TEXT_PRIMARY')};
    font-size: 11px;
    font-weight: bold;
}}
QProgressBar::chunk {{
    background-color: {c('ACCENT')};
    border-radius: 6px;
    margin: 1px;
}}

/* ============ 表格 ============ */
QTableWidget, QTableView {{
    background-color: {c('BG_CARD')};
    alternate-background-color: {c('BG_ROW_ALT')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS_SM}px;
    gridline-color: {c('BORDER')};
    selection-background-color: {c('BG_SELECT')};
    selection-color: {c('TEXT_PRIMARY')};
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 6px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {c('BG_SELECT')};
    color: {c('TEXT_PRIMARY')};
}}
QHeaderView {{
    background-color: {c('BG_PRIMARY')};
    border: none;
}}
QHeaderView::section {{
    background-color: {c('BG_ELEVATED')};
    color: {c('TEXT_SECONDARY')};
    border: none;
    border-right: 1px solid {c('BORDER')};
    border-bottom: 1px solid {c('BORDER')};
    padding: 7px 6px;
    font-size: 12px;
    font-weight: bold;
}}
QHeaderView::section:hover {{
    background-color: {c('BG_BUTTON_HOVER')};
    color: {c('TEXT_PRIMARY')};
}}
QTableCornerButton::section {{
    background-color: {c('BG_ELEVATED')};
    border: none;
}}

/* ============ 状态栏 ============ */
QStatusBar {{
    background-color: {c('BG_SIDEBAR')};
    color: {c('TEXT_SECONDARY')};
    border-top: 1px solid {c('BORDER')};
    font-size: 12px;
}}
QStatusBar::item {{
    border: none;
}}

/* ============ 标签页 ============ */
QTabWidget::pane {{
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS_SM}px;
    background-color: {c('BG_CARD')};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {c('TEXT_SECONDARY')};
    border: none;
    padding: 8px 16px;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {c('TEXT_PRIMARY')};
    border-bottom: 2px solid {c('ACCENT')};
    font-weight: bold;
}}
QTabBar::tab:hover {{
    color: {c('TEXT_PRIMARY')};
}}

/* ============ 分组框 ============ */
QGroupBox {{
    background-color: {c('BG_CARD')};
    border: 1px solid {c('BORDER')};
    border-radius: {RADIUS}px;
    margin-top: 0;
    padding: {PAD_V}px {PAD_H}px;
    font-size: 16px;
    font-weight: bold;
    color: {c('TEXT_PRIMARY')};
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 0;
    top: 4px;
    padding: 0;
    color: {c('TEXT_PRIMARY')};
    background-color: transparent;
    font-size: 16px;
    font-weight: bold;
}}

/* ============ 分割线 ============ */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    background-color: {c('BORDER')};
    border: none;
    max-height: 1px;
}}

/* ============ 菜单（主题选择器用） ============ */
QMenu {{
    background-color: {c('BG_ELEVATED')};
    color: {c('TEXT_PRIMARY')};
    border: 1px solid {c('BORDER_LIGHT')};
    border-radius: {RADIUS_SM}px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 24px 7px 14px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {c('ACCENT')};
    color: #ffffff;
}}
QMenu::separator {{
    height: 1px;
    background-color: {c('BORDER')};
    margin: 4px 8px;
}}
"""


def apply_theme(app, mode: str = DEFAULT_MODE) -> str:
    """把主题应用到整个应用。

    可反复调用以切换主题：会重建 QSS、刷新状态色、并通知已注册的监听者。

    Args:
        app: QApplication 实例。
        mode: "dark" / "light" / "system"。

    Returns:
        实际生效的主题（"dark" 或 "light"）。
    """
    global _current_mode, _palette

    _current_mode = mode if mode in MODES else DEFAULT_MODE
    effective = resolve_mode(_current_mode)
    _palette = dict(LIGHT if effective == "light" else DARK)
    refresh_colors()

    app.setStyleSheet(build_qss())
    app.setFont(base_font(10))

    # 通知监听者（表格等需要按新色值重绘单元格）
    for callback in list(_listeners):
        try:
            callback()
        except Exception:
            # 单个回调失败不应阻断主题切换
            pass

    return effective
