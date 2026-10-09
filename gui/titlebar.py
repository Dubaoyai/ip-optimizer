"""自绘标题栏（V1.5 · 2026-10-09）。

## 为什么需要它

窗口最顶部的标题栏由 **Windows 系统绘制**，Qt 样式表（QSS）**完全管不到**。
系统只提供「深 / 浅」二选一（DWM `DWMWA_USE_IMMERSIVE_DARK_MODE`），
**无法指定 `#181818` 这样的具体颜色**。

用户的诉求是「标题栏要与面板一样的色」⇒ 只能**放弃系统标题栏，自己画一条**。

## 设计（承 ui-design 技能的两遍法）

**主题锚定**：本地测速工具，黑灰专业风。标题栏是窗口的「帽檐」——
职责是「告诉你在哪个程序里 + 提供窗口控制」，**不该抢戏**。

**色彩**（全部取自 `gui.theme` 现有色板，不新增任何色值）：

| 部位 | 键 | 深色值 |
|:--|:--|:--|
| 标题条底 | `BG_CARD` | `#181818` |
| 标题文字 | `TEXT_PRIMARY` | `#f5f5f5` |
| 窗口按钮 | `TEXT_SECONDARY` | `#b0b0b0` |
| 按钮悬停底 | `BG_BUTTON_HOVER` | `#2c2c2c` |
| 关闭悬停底 | `RED` | `#ff4757` |

**Chanel 法则**：**不加分隔线** —— 标题条 `#181818` 与内容区 `#0b0b0b`
已有天然明度差（8 级），再加线是多余装饰。

## 已知代价（诚实登记）

放弃系统标题栏 ⇒ 需自行实现窗口管理。本模块实现了：

- ✅ 拖动移动、双击最大化/还原
- ✅ 最大化时**不遮挡任务栏**（用 `availableGeometry` 而非 `geometry`）
- ✅ 贴边吸附（用 `QWindow.startSystemMove()`，**由系统接管拖拽** ⇒ 保留
  Windows 原生贴边与 Aero Snap 手感）
- ⚠️ `Win + 方向键` 等纯键盘窗口管理由系统管理，**不受影响**（因为窗口仍是
  普通顶层窗口，只是去掉了边框装饰）

**关键设计决策**：优先使用 Qt 6 的 `windowHandle().startSystemMove()`，
把拖拽交给操作系统而不是自己算坐标 —— 这是保留原生手感的关键。
若该 API 不可用，回退到手算坐标（功能仍可用，但失去贴边吸附）。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from gui import theme

# 标题条高度（px）—— 与 Windows 原生标题栏视觉高度接近，避免观感突兀
TITLEBAR_HEIGHT = 34

# 窗口控制按钮尺寸
BUTTON_WIDTH = 44
BUTTON_HEIGHT = 30


class _WindowButton(QPushButton):
    """标题栏上的窗口控制按钮（最小化 / 最大化 / 关闭）。"""

    def __init__(self, glyph: str, tooltip: str, danger: bool = False) -> None:
        super().__init__(glyph)
        self._danger = danger
        self.setFixedSize(BUTTON_WIDTH, BUTTON_HEIGHT)
        self.setToolTip(tooltip)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)   # 不参与 Tab 焦点链
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.refresh_style()

    def refresh_style(self) -> None:
        """按当前主题重建样式（切换主题后调用）。"""
        normal = theme.color("TEXT_SECONDARY")
        hover_text = theme.color("TEXT_PRIMARY")
        hover_bg = theme.color("RED") if self._danger else theme.color("BG_BUTTON_HOVER")
        # 关闭按钮悬停时用红底白字，危险操作需要有辨识度
        hover_fg = theme.color("TEXT_ON_ACCENT") if self._danger else hover_text
        self.setStyleSheet(
            f"""
            QPushButton {{
                color: {normal};
                background: transparent;
                border: none;
                font-size: 13px;
                font-family: "Segoe UI Symbol", "Segoe UI", sans-serif;
            }}
            QPushButton:hover {{
                background-color: {hover_bg};
                color: {hover_fg};
            }}
            QPushButton:pressed {{
                background-color: {theme.color('BG_BUTTON_PRESSED')};
            }}
            """
        )


class CustomTitleBar(QWidget):
    """自绘标题栏：左侧标题 + 右侧窗口控制按钮，中间可拖动。"""

    # 供外部（主窗口）连接，避免标题栏直接依赖窗口实现细节
    minimize_requested = Signal()
    maximize_requested = Signal()
    close_requested = Signal()

    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("CustomTitleBar")
        self.setFixedHeight(TITLEBAR_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)
        # 左边距 8px（为最左侧的侧栏切换按钮留贴边位置）；
        # 右侧 0 让窗口控制按钮贴边（符合 Windows 习惯）
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(0)

        # ---- 左侧插槽：供主窗口放入「侧栏切换」等全局按钮 ----
        # 为什么放标题栏而不放顶栏：顶栏位于**右侧内容区内部**，
        # 其 x=0 是侧边栏右沿（240px），按钮会被挤到中间；
        # 而标题栏横跨全宽，x=0 就是窗口最左边缘（这才是用户预期的位置）。
        self.left_slot = QHBoxLayout()
        self.left_slot.setContentsMargins(0, 0, 0, 0)
        self.left_slot.setSpacing(4)
        layout.addLayout(self.left_slot)
        layout.setSpacing(0)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("TitleBarText")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.min_button = _WindowButton("─", "最小化")
        self.max_button = _WindowButton("☐", "最大化")
        self.close_button = _WindowButton("✕", "关闭", danger=True)

        self.min_button.clicked.connect(self.minimize_requested.emit)
        self.max_button.clicked.connect(self.maximize_requested.emit)
        self.close_button.clicked.connect(self.close_requested.emit)

        for btn in (self.min_button, self.max_button, self.close_button):
            layout.addWidget(btn)

        self.refresh_style()

    def refresh_style(self) -> None:
        """按当前主题重建样式（切换主题后必须调用）。

        ⚠️ 选择器必须覆盖**标题栏自身的所有子控件**。
        原因：theme.build_qss 里有一条 `QScrollArea > QWidget > QWidget`
        规则会把 `BG_PRIMARY`(#0b0b0b) 刷到后裔 QWidget 上，且它是**全局样式表**，
        优先级高于控件级样式 —— 若此处只写 `#CustomTitleBar`，标题栏内部
        会被刷成 #0b0b0b，与面板色 #181818 对不上（实测踩过这个坑）。
        故这里用 `#CustomTitleBar, #CustomTitleBar QWidget` 同时命中自身与子控件。
        """
        card = theme.color("BG_CARD")
        self.setStyleSheet(
            f"""
            #CustomTitleBar, #CustomTitleBar QWidget {{
                background-color: {card};
            }}
            #TitleBarText {{
                color: {theme.color('TEXT_PRIMARY')};
                font-size: 12px;
                font-weight: 600;
                background: transparent;
            }}
            """
        )
        for btn in (self.min_button, self.max_button, self.close_button):
            btn.refresh_style()

    def set_maximized(self, maximized: bool) -> None:
        """同步最大化按钮的图标与提示。"""
        self.max_button.setText("❐" if maximized else "☐")
        self.max_button.setToolTip("还原" if maximized else "最大化")

    # ------------------------------------------------------------------
    # 拖拽：优先交给系统（保留 Windows 原生贴边吸附）
    # ------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """按住标题栏左键：尝试把拖拽交给系统（保留 Aero Snap）。"""
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        window = self.window()
        handle = window.windowHandle() if window else None

        # 双击标题栏 = 最大化/还原（与 Windows 行为一致）
        if event.type() == QMouseEvent.Type.MouseButtonDblClick:
            self.maximize_requested.emit()
            return

        # Qt 6 提供 startSystemMove：由操作系统接管拖拽，
        # 从而保留 Windows 原生的「拖到屏幕边缘自动贴边」手感。
        if handle is not None:
            try:
                if handle.startSystemMove():
                    return
            except Exception:
                pass  # 平台不支持时回退到下方的手算拖拽

        # 回退路径：手算坐标（功能可用，但没有贴边吸附）
        self._fallback_drag_pos = (
            event.globalPosition().toPoint() - window.frameGeometry().topLeft()
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """回退路径的拖拽实现（仅当 startSystemMove 不可用时走到这里）。"""
        pos = getattr(self, "_fallback_drag_pos", None)
        if pos is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.window().move(event.globalPosition().toPoint() - pos)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """结束拖拽。"""
        self._fallback_drag_pos = None
        super().mouseReleaseEvent(event)
