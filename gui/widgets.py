"""黑灰主题的可复用界面组件。

参照《API总代理》的视觉语言，把反复出现的三种构件抽成类：
1. `NavButton`    —— 侧边栏导航按钮（选中态左侧紫色竖条）；
2. `StatCard`     —— 统计卡片（小标签 + 大数字 + 右上角大图标水印）；
3. `Panel`        —— 圆角面板容器（面板头：标题 + 右侧动作区；下方分隔线 + 内容区）；
4. `SectionTitle` / `HintLabel` —— 统一的文字层级控件；
5. `Divider`      —— 1px 分隔线。

所有颜色/尺寸一律取自 gui.theme，本文件不出现字面量色值（图标水印除外，
它们用的是主题里的常量）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui import theme


# ======================================================================
# 侧边栏导航按钮
# ======================================================================
class NavButton(QPushButton):
    """侧边栏导航按钮：可选中，选中时左侧显示紫色竖条。"""

    def __init__(self, text: str, icon_text: str = "", parent: Optional[QWidget] = None) -> None:
        """初始化导航按钮。

        Args:
            text: 按钮文字（中文）。
            icon_text: 前置图标字符（用 Unicode 符号，避免引入图片资源）。
            parent: 父控件。
        """
        super().__init__(f"  {icon_text}   {text}" if icon_text else f"  {text}", parent)
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(38)


# ======================================================================
# 统计卡片
# ======================================================================
class StatCard(QWidget):
    """统计卡片：上排「小标签」，下排「大数字 + 单位」，右上角一个淡色大图标水印。"""

    def __init__(
        self,
        label: str,
        value: str = "0",
        unit: str = "",
        icon_text: str = "",
        accent_key: str = "TEXT_PRIMARY",
        parent: Optional[QWidget] = None,
    ) -> None:
        """初始化统计卡片。

        Args:
            label: 指标名称（如「有效 IP」）。
            value: 指标数值（字符串，便于显示「—」等占位）。
            unit: 数值单位（如「个」，可空）。
            icon_text: 右上角水印图标字符（可空）。
            accent_key: 数值颜色在主题色板中的键名（默认主文字色，可传 GREEN 等状态色）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setMinimumHeight(92)
        # Qt 陷阱：自定义 QWidget 子类默认不绘制 QSS 的背景与边框，
        # 必须显式打开 WA_StyledBackground，否则 #StatCard 的 border/background 全部失效。
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # 排版对齐《API总代理》.stat-card：padding 14px 18px
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.CARD_PAD_H, theme.CARD_PAD_V, theme.CARD_PAD_H, theme.CARD_PAD_V)
        outer.setSpacing(6)

        # 上排：小标签（左） + 图标水印（右）
        # 用布局而非绝对定位——绝对定位在 Qt 中会与布局时机打架（图标会跑到数值区）。
        top = QHBoxLayout()
        top.setSpacing(6)
        self._label = QLabel(label)
        self._label.setObjectName("StatLabel")
        top.addWidget(self._label)
        top.addStretch(1)
        if icon_text:
            icon = QLabel(icon_text)
            # 图标水印：对齐《API总代理》.stat-icon 的极淡观感。
            # Qt 的 QSS 不支持 opacity，故色板里用 rgba 半透明色代替。
            icon.setStyleSheet(
                f"color: {theme.color('WATERMARK')};"
                "background: transparent; font-size: 22px;"
            )
            icon.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            top.addWidget(icon)
        outer.addLayout(top)

        # 下排：大数字 + 单位
        bottom = QHBoxLayout()
        bottom.setSpacing(5)
        self._accent_key = accent_key
        self._value = QLabel(value)
        self._value.setObjectName("StatValue")
        self._value.setStyleSheet(
            f"color: {theme.color(accent_key)}; background: transparent;"
        )
        bottom.addWidget(self._value)
        self._unit = QLabel(unit)
        self._unit.setObjectName("StatUnit")
        self._unit.setAlignment(Qt.AlignmentFlag.AlignBottom)
        bottom.addWidget(self._unit)
        bottom.addStretch(1)
        outer.addLayout(bottom)
        outer.addStretch(1)

        # 主题切换时按新色板重绘数值颜色与水印
        theme.on_changed(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        """主题切换回调：按当前色板重设数值颜色（保持原有强调键）。"""
        self._value.setStyleSheet(
            f"color: {theme.color(self._accent_key)}; background: transparent;"
        )

    def set_value(self, value: str, accent_key: Optional[str] = None) -> None:
        """更新卡片数值。

        Args:
            value: 新的数值文本。
            accent_key: 可选的新强调色键名，不传则保持原色。
        """
        self._value.setText(value)
        if accent_key is not None:
            self._accent_key = accent_key
        self._value.setStyleSheet(
            f"color: {theme.color(self._accent_key)}; background: transparent;"
        )


# ======================================================================
# 面板容器
# ======================================================================
class Panel(QWidget):
    """圆角面板：面板头（标题 + 右侧动作区）+ 可选副标题 + 分隔线 + 内容区。

    用法：
        panel = Panel("IP 来源", subtitle="导入或自动获取候选 IP")
        panel.add_action(button)          # 往面板头右侧加按钮
        panel.body_layout.addWidget(...)  # 往内容区加控件
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        """初始化面板。

        Args:
            title: 面板标题。
            subtitle: 标题右侧的灰色说明文字（可空）。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setObjectName("Card")
        # Qt 陷阱：自定义 QWidget 子类默认不绘制 QSS 的背景与边框，
        # 必须显式打开 WA_StyledBackground，否则 #Card 的 border/background 全部失效。
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # 排版对齐《API总代理》.panel：padding 18px 22px
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.PAD_H, theme.PAD_V, theme.PAD_H, theme.PAD_V)
        outer.setSpacing(theme.HEADER_GAP)

        # ---- 面板头 ----
        header = QWidget()
        header.setObjectName("PanelHeader")
        header.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("PanelTitle")
        header_layout.addWidget(self.title_label)

        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("Muted")
            header_layout.addWidget(self.subtitle_label)

        header_layout.addStretch(1)

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(8)
        header_layout.addLayout(self._actions_layout)

        outer.addWidget(header)

        # ---- 分隔线 ----
        outer.addWidget(Divider())

        # ---- 内容区 ----
        self.body = QWidget()
        self.body.setObjectName("PanelHeader")  # 透明背景
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(10)
        outer.addWidget(self.body)
        outer.addStretch(0)

    def add_action(self, widget: QWidget) -> None:
        """往面板头右侧添加一个控件（通常是按钮）。

        Args:
            widget: 要添加的控件。
        """
        self._actions_layout.addWidget(widget)

    def set_title(self, title: str) -> None:
        """更新面板标题。"""
        self.title_label.setText(title)


# ======================================================================
# 基础文字 / 分隔件
# ======================================================================
class Divider(QFrame):
    """1px 水平分隔线（用固定高度 + 背景色实现，比 frameShape 更可控）。"""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("PanelDivider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        # 直接设置内联样式，避免依赖 frameShape 在深色主题下的默认渲染
        self.setStyleSheet(
            f"background-color: {theme.color('BORDER')}; border: none; max-height: 1px;"
        )
        theme.on_changed(self._on_theme_changed)

    def _on_theme_changed(self) -> None:
        """主题切换回调：重设分隔线颜色。"""
        self.setStyleSheet(
            f"background-color: {theme.color('BORDER')}; border: none; max-height: 1px;"
        )


def section_title(text: str) -> QLabel:
    """构造一个小节标题标签。"""
    label = QLabel(text)
    label.setObjectName("PanelTitle")
    return label


def hint_label(text: str = "", tone: str = "muted") -> QLabel:
    """构造提示文字标签。

    Args:
        text: 提示内容。
        tone: 语气 —— "muted"（默认灰）/ "secondary" / "success" / "warning" / "danger"。
    """
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName({
        "muted": "Muted",
        "secondary": "Secondary",
        "success": "Success",
        "warning": "Warning",
        "danger": "Danger",
    }.get(tone, "Muted"))
    return label


def primary_button(text: str, tooltip: str = "") -> QPushButton:
    """构造主按钮（紫底）。"""
    button = QPushButton(text)
    button.setObjectName("PrimaryButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


def danger_button(text: str, tooltip: str = "") -> QPushButton:
    """构造危险按钮（红底，用于停止）。"""
    button = QPushButton(text)
    button.setObjectName("DangerButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button


def ghost_button(text: str, tooltip: str = "") -> QPushButton:
    """构造幽灵按钮（透明底描边，次要动作）。"""
    button = QPushButton(text)
    button.setObjectName("GhostButton")
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    if tooltip:
        button.setToolTip(tooltip)
    return button
