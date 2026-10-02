"""黑灰主题（Dark Theme）—— 全项目唯一的配色与样式真源。

设计基准：参照本机《API总代理》的视觉语言 1:1 复刻 ——
左侧边栏 + 顶栏 + 统计卡片行 + 圆角面板，近黑底 + 紫色强调色。

约定：
1. 所有颜色**只在本文件定义**，其他模块一律 `from gui.theme import ...` 引用，
   禁止在界面代码里再写字面量十六进制色值（防止配色漂移）。
2. 尺寸/圆角/间距同样集中在此，改一处即全界面生效。
3. 字体族按 Windows 中文环境优先选「微软雅黑」，回退链保证跨机器不豆腐块。
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont

# ======================================================================
# 一、设计令牌（Design Tokens）—— 与《API总代理》CSS 变量逐项对应
# ======================================================================

# ---- 背景层级：越靠上层的元素越亮，形成黑灰纵深 ----
BG_PRIMARY = "#0b0b0b"      # 最底层：窗口背景
BG_SECONDARY = "#111111"    # 次底层
BG_CARD = "#181818"         # 卡片 / 面板底
BG_CARD_HOVER = "#202020"   # 卡片悬停
BG_INPUT = "#1e1e1e"        # 输入框 / 下拉框底
BG_SIDEBAR = "#0e0e0e"      # 侧边栏底
BG_ELEVATED = "#232323"     # 悬浮层（表头 / 弹窗按钮）

# ---- 描边 ----
BORDER = "#282828"          # 常规描边
BORDER_LIGHT = "#3a3a3a"    # 悬停 / 强调描边

# ---- 文字层级 ----
TEXT_PRIMARY = "#f5f5f5"    # 主文字
TEXT_SECONDARY = "#b0b0b0"  # 次要文字
TEXT_MUTED = "#6a6a6a"      # 弱化文字 / 占位符

# ---- 强调色 ----
ACCENT = "#7c6cf0"          # 主强调：紫
ACCENT_HOVER = "#9a8cf5"
ACCENT_PRESSED = "#5b4ad0"

# ---- 状态色 ----
GREEN = "#00d4aa"           # 成功 / 优秀
ORANGE = "#ffa502"          # 警告 / 一般
RED = "#ff4757"             # 失败 / 差
BLUE = "#4ea1ff"            # 信息

# ---- 尺寸（数值取自《API总代理》的排版规范，逐项对应） ----
RADIUS = 14                 # 大圆角（卡片 / 面板）—— .stat-card / .panel 的 --radius
RADIUS_SM = 8               # 小圆角（按钮 / 输入框）—— .nav-item 的 --radius-sm
SIDEBAR_WIDTH = 240         # 侧边栏宽 —— .sidebar width: 240px
BRAND_ICON = 56             # 品牌图标边长 —— .logo-icon 56×56
BRAND_RADIUS = 14           # 品牌图标圆角
PAD_H = 22                  # 面板横向内边距 —— .panel padding: 18px 22px
PAD_V = 18                  # 面板纵向内边距
CARD_PAD_H = 18             # 统计卡片横向内边距 —— .stat-card padding: 14px 18px
CARD_PAD_V = 14             # 统计卡片纵向内边距
GAP = 12                    # 栅格间距 —— .stats-grid gap: 12px
GAP_CARD = 20               # 卡片之间的纵向间距 —— .panel margin-bottom: 20px
MAIN_PAD_H = 28             # 主内容区横向内边距 —— .main padding: 20px 28px 28px 28px
MAIN_PAD_V = 20             # 主内容区纵向内边距
HEADER_GAP = 14             # 面板头与内容的下间距 —— .panel-header margin-bottom: 14px
TOPBAR_GAP = 20             # 顶栏与下方内容的下间距 —— .topbar margin-bottom: 20px
TOPBAR_H = 64               # 顶栏高度

# ---- 字体 ----
FONT_FAMILY = '"Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI", sans-serif'
FONT_MONO = '"Cascadia Mono", "Consolas", monospace'


# ======================================================================
# 二、QColor 常量（供表格上色等需要 QColor 的场合使用）
# ======================================================================

def qcolor(hex_value: str) -> QColor:
    """把十六进制色串转成 QColor（供表格 setForeground 等使用）。"""
    return QColor(hex_value)


# 表格用色：与主题令牌保持一致，但采用稍柔和的版本以便在深底上长时间阅读
COLOR_SUCCESS = QColor(GREEN)
COLOR_WARNING = QColor(ORANGE)
COLOR_FAILED = QColor(RED)
COLOR_MUTED = QColor(TEXT_MUTED)
COLOR_PRIMARY = QColor(TEXT_PRIMARY)
COLOR_ACCENT = QColor(ACCENT)


def base_font(size: int = 10, bold: bool = False) -> QFont:
    """构造主题基准字体（统一字体族，避免各控件字体不一致）。"""
    font = QFont()
    font.setFamilies(["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"])
    font.setPointSize(size)
    font.setBold(bold)
    return font


# ======================================================================
# 三、QSS 样式表 —— 全局应用一次即可（QApplication.setStyleSheet）
# ======================================================================

QSS = f"""
/* ============ 全局基础 ============ */
/* 注意：只给顶层窗口与容器设底色，**不要**给裸 QWidget 设 background-color——
   否则卡片内部的 QLabel 等子控件会各带一块不透明底色，在卡片上形成突兀的黑条。 */
QMainWindow, QDialog {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QWidget {{
    color: {TEXT_PRIMARY};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}
QLabel {{
    background: transparent;
    color: {TEXT_PRIMARY};
}}
QToolTip {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ============ 滚动条：细窄、悬停变亮 ============ */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {ACCENT};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_LIGHT};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {ACCENT};
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
    background-color: {BG_PRIMARY};
}}
QScrollArea > QWidget > QWidget {{
    background-color: {BG_PRIMARY};
}}
/* 页面容器与卡片内部一律透明，底色只由 Card / StatCard / Sidebar 承担 */
QWidget#PageContainer {{
    background-color: transparent;
}}

/* ============ 侧边栏 ============ */
#Sidebar {{
    background-color: {BG_SIDEBAR};
    border-right: 1px solid {BORDER};
}}
#SidebarBrand {{
    background-color: {BG_SIDEBAR};
}}
#BrandTitle {{
    color: {TEXT_PRIMARY};
    font-size: 19px;
    font-weight: bold;
    background: transparent;
}}
#BrandSub {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 500;
    background: transparent;
}}
#BrandIcon {{
    background-color: {ACCENT};
    color: #ffffff;
    border-radius: {BRAND_RADIUS}px;
    font-size: 17px;
    font-weight: bold;
}}
#SidebarDivider {{
    background-color: {BORDER};
    max-height: 1px;
    border: none;
}}
#SidebarSection {{
    color: {TEXT_MUTED};
    font-size: 11px;
    padding: 10px 14px 4px 14px;
    background: transparent;
}}
QPushButton#NavButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    border-left: 3px solid transparent;
    border-radius: 0;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
}}
QPushButton#NavButton:hover {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
}}
QPushButton#NavButton:checked {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border-left: 3px solid {ACCENT};
    font-weight: bold;
}}

/* ============ 顶栏 ============ */
#TopBar {{
    background-color: {BG_PRIMARY};
    border-bottom: 1px solid {BORDER};
}}
#PageTitle {{
    color: {TEXT_PRIMARY};
    font-size: 20px;
    font-weight: bold;
    background: transparent;
}}
#PageSubtitle {{
    color: {TEXT_MUTED};
    font-size: 13px;
    background: transparent;
}}

/* ============ 卡片 / 面板 ============ */
/* 注意：QT 的样式继承顺序要求 #Card 这类 ID 选择器置于 QWidget 通用规则之后，
   且需要显式写 background-color 与 border 才不会被 QWidget 规则覆盖。 */
QWidget#Card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QWidget#StatCard {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
}}
QWidget#StatCard:hover {{
    background-color: {BG_CARD_HOVER};
    border: 1px solid {BORDER_LIGHT};
}}
QWidget#PanelHeader {{
    background-color: transparent;
    border: none;
}}
QFrame#PanelDivider {{
    background-color: {BORDER};
    border: none;
    max-height: 1px;
}}
#StatLabel {{
    color: {TEXT_MUTED};
    font-size: 11px;
    font-weight: 500;
    background: transparent;
}}
#StatValue {{
    color: {TEXT_PRIMARY};
    font-size: 26px;
    font-weight: bold;
    background: transparent;
}}
#StatUnit {{
    color: {TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}
#PanelTitle {{
    color: {TEXT_PRIMARY};
    font-size: 16px;
    font-weight: bold;
    background: transparent;
}}

/* ============ 文字层级（通用） ============ */
#Muted {{
    color: {TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}
#Secondary {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
    background: transparent;
}}
#Hint {{
    color: {TEXT_MUTED};
    font-size: 12px;
    background: transparent;
}}
#Success {{
    color: {GREEN};
    font-size: 12px;
    background: transparent;
}}
#Warning {{
    color: {ORANGE};
    font-size: 12px;
    background: transparent;
}}
#Danger {{
    color: {RED};
    font-size: 12px;
    background: transparent;
}}

/* ============ 按钮：三种层级 ============ */
QPushButton {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_SM}px;
    padding: 7px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: #2c2c2c;
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: #161616;
}}
QPushButton:disabled {{
    background-color: #161616;
    color: #4a4a4a;
    border-color: {BORDER};
}}

/* 主按钮（紫底）：用于「开始」这类主行动 */
QPushButton#PrimaryButton {{
    background-color: {ACCENT};
    color: #ffffff;
    border: 1px solid {ACCENT};
    font-weight: bold;
}}
QPushButton#PrimaryButton:hover {{
    background-color: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#PrimaryButton:pressed {{
    background-color: {ACCENT_PRESSED};
}}
QPushButton#PrimaryButton:disabled {{
    background-color: #2a2640;
    color: #6b6580;
    border-color: #2a2640;
}}

/* 危险按钮（红底）：用于「停止」 */
QPushButton#DangerButton {{
    background-color: {RED};
    color: #ffffff;
    border: 1px solid {RED};
    font-weight: bold;
}}
QPushButton#DangerButton:hover {{
    background-color: #ff6272;
    border-color: #ff6272;
}}
QPushButton#DangerButton:pressed {{
    background-color: #d93a49;
}}
QPushButton#DangerButton:disabled {{
    background-color: #3a2026;
    color: #7a5560;
    border-color: #3a2026;
}}

/* 幽灵按钮：次要动作 */
QPushButton#GhostButton {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: 1px solid {BORDER_LIGHT};
}}
QPushButton#GhostButton:hover {{
    background-color: {BG_CARD_HOVER};
    color: {TEXT_PRIMARY};
    border-color: {ACCENT};
}}

/* ============ 输入控件 ============ */
QLineEdit, QPlainTextEdit, QTextEdit {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 7px 10px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled, QPlainTextEdit:disabled {{
    background-color: #141414;
    color: #5a5a5a;
}}
QLineEdit[readOnly="true"] {{
    background-color: #141414;
    color: {TEXT_SECONDARY};
}}

/* 数字输入框：隐藏原生上下箭头（太扎眼），保留键盘与滚轮调节 */
QSpinBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 6px 8px;
    min-width: 60px;
}}
QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QSpinBox:disabled {{
    background-color: #141414;
    color: #5a5a5a;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    width: 0;
    border: none;
}}

/* 下拉框 */
QComboBox {{
    background-color: {BG_INPUT};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    padding: 6px 10px;
    min-width: 70px;
}}
QComboBox:hover {{
    border-color: {BORDER_LIGHT};
}}
QComboBox:focus, QComboBox:on {{
    border: 1px solid {ACCENT};
}}
QComboBox:disabled {{
    background-color: #141414;
    color: #5a5a5a;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_SECONDARY};
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_ELEVATED};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_LIGHT};
    border-radius: {RADIUS_SM}px;
    padding: 4px;
    outline: none;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}

/* ============ 复选框 / 单选框 ============ */
QCheckBox, QRadioButton {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
    background: transparent;
    padding: 3px 0;
}}
QCheckBox:disabled, QRadioButton:disabled {{
    color: #5a5a5a;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {BORDER_LIGHT};
    background-color: {BG_INPUT};
}}
QCheckBox::indicator {{
    border-radius: 4px;
}}
QRadioButton::indicator {{
    border-radius: 8px;
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {ACCENT};
}}
QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}
QRadioButton::indicator:checked {{
    background-color: {ACCENT};
    border: 4px solid {BG_INPUT};
    outline: 1px solid {ACCENT};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: #141414;
    border-color: #333333;
}}

/* ============ 进度条 ============ */
QProgressBar {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    height: 20px;
    text-align: center;
    color: {TEXT_PRIMARY};
    font-size: 11px;
    font-weight: bold;
}}
QProgressBar::chunk {{
    background-color: {ACCENT};
    border-radius: 6px;
    margin: 1px;
}}

/* ============ 表格 ============ */
QTableWidget, QTableView {{
    background-color: {BG_CARD};
    alternate-background-color: #1c1c1c;
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    gridline-color: {BORDER};
    selection-background-color: #2a2640;
    selection-color: {TEXT_PRIMARY};
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: 5px 6px;
    border: none;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: #2a2640;
    color: {TEXT_PRIMARY};
}}
QHeaderView {{
    background-color: {BG_PRIMARY};
    border: none;
}}
QHeaderView::section {{
    background-color: {BG_ELEVATED};
    color: {TEXT_SECONDARY};
    border: none;
    border-right: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    padding: 7px 6px;
    font-size: 12px;
    font-weight: bold;
}}
QHeaderView::section:hover {{
    background-color: #2c2c2c;
    color: {TEXT_PRIMARY};
}}
QTableCornerButton::section {{
    background-color: {BG_ELEVATED};
    border: none;
}}

/* ============ 状态栏 ============ */
QStatusBar {{
    background-color: {BG_SIDEBAR};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 12px;
}}
QStatusBar::item {{
    border: none;
}}

/* ============ 标签页（对话框内可能用到） ============ */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    border-radius: {RADIUS_SM}px;
    background-color: {BG_CARD};
}}
QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    border: none;
    padding: 8px 16px;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT};
    font-weight: bold;
}}
QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}

/* ============ 分组框（充当卡片容器；标题即面板头） ============ */
QGroupBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: {RADIUS}px;
    margin-top: 0;                 /* 标题改为内嵌式，不再悬浮在边框上 */
    padding: {PAD_V}px {PAD_H}px;
    font-size: 16px;
    font-weight: bold;
    color: {TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: padding;
    subcontrol-position: top left;
    left: 0;
    top: 4px;
    padding: 0;
    color: {TEXT_PRIMARY};
    background-color: transparent;
    font-size: 16px;
    font-weight: bold;
}}

/* ============ 分割线 ============ */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    background-color: {BORDER};
    border: none;
    max-height: 1px;
}}
"""


def apply_theme(app) -> None:
    """把主题应用到整个应用（在 QApplication 创建后立即调用一次）。

    Args:
        app: QApplication 实例。
    """
    app.setStyleSheet(QSS)
    app.setFont(base_font(10))


def restyle(widget) -> None:
    """对单个控件重新应用样式（动态创建、后加入界面的控件用）。

    Args:
        widget: 任意 QWidget。
    """
    widget.setStyleSheet(QSS)
