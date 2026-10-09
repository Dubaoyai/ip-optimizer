"""主窗口。

负责界面布局和用户交互：
1. 导入 IP（文件 / 粘贴）并显示统计信息；
2. 设置端口、并发、超时；
3. 开始 / 停止测速，显示进度；
4. 显示结果（按延迟排序）。

所有耗时的网络操作都交给 ScanWorker 线程执行，主线程只负责刷新界面，
所以测速过程中窗口依然可以正常拖动、点击，不会出现“未响应”。
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from core.ip_loader import IPEntry
from core.ranking import (
    DEFAULT_TOP_N,
    LATENCY_FILTER_OPTIONS,
    SPEED_FILTER_OPTIONS,
    TOP_OPTIONS,
    build_final_ranking,
    build_ranking,
)
from core.scanner import (
    DEFAULT_CONCURRENCY,
    DEFAULT_DOWNLOAD_BYTES,
    DEFAULT_DOWNLOAD_TIMEOUT_MS,
    DEFAULT_HTTP_TIMEOUT_MS,
    DEFAULT_TIMEOUT_MS,
    MAX_CONCURRENCY,
    MAX_DOWNLOAD_TIMEOUT_MS,
    MAX_HTTP_TIMEOUT_MS,
    MAX_TIMEOUT_MS,
    MIN_CONCURRENCY,
    MIN_DOWNLOAD_TIMEOUT_MS,
    MIN_HTTP_TIMEOUT_MS,
    MIN_TIMEOUT_MS,
    StageStats,
    ScanSummary,
)
from core.stability import StabilityData  # V1.4：稳定性复测统计数据结构
from core.tcp_tester import TestResult
from gui import theme, titlebar, widgets
from gui.ip_panel import IPPanel
from gui.sample_page import SamplePage
from gui.result_table import ResultTable
from gui.scan_worker import ScanWorker
from gui.stability_worker import StabilityWorker  # V1.4：稳定性复测线程
from utils.export import (
    ExportError,
    export_csv,
    export_nodes,
    export_plain_text,
    export_stable_csv,
    export_stable_txt,
    export_txt,
)
from utils.logger import get_logger
from utils.paths import data_root

logger: logging.Logger = get_logger()

APP_TITLE = "IP优化器"

# 结果批量刷新间隔（毫秒）：测速时先把结果攒起来，定时批量写入表格，界面更流畅
RESULT_FLUSH_INTERVAL_MS = 300

# 用时刷新间隔（毫秒）：即使某个批次都在等待超时，界面上的“用时”也会持续走动
ELAPSED_REFRESH_INTERVAL_MS = 200

DEFAULT_PORT = 443

# 下载大小的下拉选项（文本，字节）：方便初学者直接选择，不用自己换算
DOWNLOAD_SIZE_OPTIONS = (
    ("256 KB", 256 * 1024),
    ("512 KB", 512 * 1024),
    ("1 MB", 1024 * 1024),
    ("2 MB", 2 * 1024 * 1024),
    ("5 MB", 5 * 1024 * 1024),
)

# V1.4：稳定性复测的选项（复测轮数 3/5/10，默认 5；复测并发 10/20/50，默认 20）
STABILITY_ROUND_OPTIONS = (3, 5, 10)
DEFAULT_STABILITY_ROUNDS = 5
STABILITY_CONCURRENCY_OPTIONS = (10, 20, 50)
DEFAULT_STABILITY_CONCURRENCY = 20
# 稳定性评分达到该值视为“稳定”（结果摘要里统计稳定/波动数量用）
STABLE_SCORE_THRESHOLD = 60


class MainWindow(QMainWindow):
    """程序主窗口。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle(APP_TITLE)
        self.resize(1080, 860)
        self.setMinimumSize(900, 660)

        # ---- 无边框窗口（V1.5：自绘标题栏的前提）----
        # 去掉 Windows 原生标题栏后，改由 gui/titlebar.py 自绘一条，
        # 使其颜色能与面板**像素级同色**（系统标题栏无法指定 #181818）。
        # 保留 Window 标志 ⇒ 仍是普通顶层窗口：任务栏显示、Alt+Tab、
        # Win+方向键等系统行为不受影响。
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        # 记录「最大化前的窗口几何」，供还原时恢复
        self._normal_geometry: Optional[QRect] = None

        # ---- 消除启动白闪（2026-10-09 用户反馈「刚弹出来是白色主题」）----
        # 问题：QSS 是异步生效的。窗口在 show() 的第一帧会先按 Windows 默认
        #       画成白色，之后样式表才覆盖上来 —— 用户看到一次刺眼的白闪。
        # 做法：在构造期就直接把窗口自身的调色板底色设成当前主题的 BG_PRIMARY，
        #       使第一帧就是深色。QSS 仍照常生效，两者不冲突。
        self._apply_window_base_color()

        # 运行时数据
        self._valid_entries: List[IPEntry] = []           # 导入并校验通过、可测速的 IP
        self._pending_results: List[TestResult] = []      # 等待写入表格的结果
        self._all_results: List[TestResult] = []          # 本轮测速的全部结果
        self._worker: Optional[ScanWorker] = None         # 测速线程
        self._scan_start_time: float = 0.0                # 测速开始时间
        self._quit_timer: Optional[QTimer] = None         # 退出前检查线程是否结束
        self._running = False                             # 是否正在主测速（判断控件可用性用）
        # V1.4 复测/排名运行时数据
        self._stability_worker: Optional[StabilityWorker] = None   # 复测线程
        self._stability_map: Dict[str, StabilityData] = {}         # {ip: StabilityData}
        self._stability_running = False                            # 复测是否进行中
        self._stab_results_all: List[TestResult] = []              # 已完成轮次的原始结果（复测出现问题时供复查用）
        self._stab_rounds_total = 0                                # 本次复测计划轮数（进度显示用）
        self._stab_ip_total = 0                                    # 本次复测目标 IP 数（进度显示用）

        # 定时器：批量刷新结果表格
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(RESULT_FLUSH_INTERVAL_MS)
        self._flush_timer.timeout.connect(self._flush_results)

        # 定时器：测速过程中持续刷新“用时”
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(ELAPSED_REFRESH_INTERVAL_MS)
        self._elapsed_timer.timeout.connect(self._refresh_elapsed)

        self._build_ui()
        logger.info("软件启动：主窗口创建完成")

    # ==================================================================
    # 界面搭建（黑灰主题 · 参照《API总代理》视觉语言重排版）
    # ==================================================================
    def _build_ui(self) -> None:
        """搭建主界面：左侧边栏 + 右侧（顶栏 + 统计卡片行 + 滚动内容区）。

        重排版说明（V2.0 界面重构）：
        - 原「一列 GroupBox 竖着堆」的布局改为「侧边栏切换视图 + 卡片面板」；
        - 所有控件的变量名与信号连接与原版**完全一致**，业务逻辑零改动；
        - 视图切换只是把面板加进/移出布局，控件对象始终存在，数据不丢。
        """
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---------------- 自绘标题栏（V1.5） ----------------
        # 系统标题栏由 Windows 绘制，QSS 管不到、也无法指定 #181818；
        # 故改为无边框窗口 + 自绘标题条，使其与面板**像素级同色**。
        self.title_bar = titlebar.CustomTitleBar(APP_TITLE)
        self.title_bar.minimize_requested.connect(self.showMinimized)
        self.title_bar.maximize_requested.connect(self._toggle_maximized)
        self.title_bar.close_requested.connect(self.close)
        outer.addWidget(self.title_bar)

        body = QWidget()
        root = QHBoxLayout(body)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------------- 左侧边栏 ----------------
        root.addWidget(self._build_sidebar())

        # ---------------- 右侧主区 ----------------
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        right_layout.addWidget(self._build_topbar())

        # 内容滚动区（排版对齐《API总代理》.main：padding 20px 28px 28px 28px）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._content_host = QWidget()
        self._content_layout = QVBoxLayout(self._content_host)
        self._content_layout.setContentsMargins(
            theme.MAIN_PAD_H, theme.MAIN_PAD_V, theme.MAIN_PAD_H, theme.MAIN_PAD_H
        )
        self._content_layout.setSpacing(theme.GAP_CARD)
        scroll.setWidget(self._content_host)
        right_layout.addWidget(scroll, 1)

        root.addWidget(right, 1)
        outer.addWidget(body, 1)
        self.setCentralWidget(central)

        # 构建视图页面容器（顺序与侧边栏导航一致：工作台 → 稳定性复测 → 测试结果 → 抽样测速）
        self._build_stat_cards()
        self._pages: Dict[str, QWidget] = {}
        self._pages["workbench"] = self._build_workbench_page()
        self._pages["stability"] = self._build_stability_page()
        self._pages["results"] = self._build_results_page()
        # 第四视图：抽样测速（移植自《优选IP测速_重构版.html》）
        self.sample_page = SamplePage()
        self._pages["sample"] = self.sample_page

        # 把页面都加进内容区，靠显示/隐藏切换
        for page in self._pages.values():
            self._content_layout.addWidget(page)
        self._content_layout.addStretch(1)

        # 默认显示工作台
        self._switch_view("workbench")
        self._set_status("就绪：请先导入 IP")

    # ------------------------------------------------------------------
    # 左侧边栏
    # ------------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        """构建左侧边栏：品牌区 + 导航 + 底部状态。"""
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(theme.SIDEBAR_WIDTH)
        layout = QVBoxLayout(side)
        # 对齐《API总代理》.sidebar：padding 20px 14px
        layout.setContentsMargins(14, 20, 14, 14)
        layout.setSpacing(0)

        # ---- 品牌区（对齐《API总代理》.sidebar-brand：padding 0 6px 18px 6px，图标 56×56） ----
        brand = QWidget()
        brand.setObjectName("SidebarBrand")
        brand_layout = QHBoxLayout(brand)
        brand_layout.setContentsMargins(6, 0, 6, 16)
        brand_layout.setSpacing(12)

        logo = QLabel("IP")
        logo.setObjectName("BrandIcon")
        logo.setFixedSize(theme.BRAND_ICON, theme.BRAND_ICON)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand_layout.addWidget(logo)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        title = QLabel("IP优化器")
        title.setObjectName("BrandTitle")
        sub = QLabel("本地测速 · 优选")
        sub.setObjectName("BrandSub")
        text_box.addWidget(title)
        text_box.addWidget(sub)
        brand_layout.addLayout(text_box)
        brand_layout.addStretch(1)
        layout.addWidget(brand)

        layout.addWidget(widgets.Divider())

        # ---- 导航 ----
        nav_label = QLabel("功能导航")
        nav_label.setObjectName("SidebarSection")
        layout.addWidget(nav_label)

        self._nav_buttons: Dict[str, widgets.NavButton] = {}
        # 顺序按使用流程排列：先测速 → 再复测取稳定 → 再看排名结果 → 抽样生成节点
        nav_items = (
            ("workbench", "工作台", "▶"),
            ("stability", "稳定性复测", "◈"),
            ("results", "测试结果", "▤"),
            ("sample", "抽样测速", "◇"),
        )
        for key, text, icon in nav_items:
            button = widgets.NavButton(text, icon)
            button.clicked.connect(lambda _checked=False, k=key: self._switch_view(k))
            self._nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)

        # ---- 底部状态 ----
        layout.addWidget(widgets.Divider())
        self.sidebar_status = QLabel("● 就绪")
        self.sidebar_status.setObjectName("Muted")
        self.sidebar_status.setContentsMargins(4, 12, 4, 4)
        layout.addWidget(self.sidebar_status)

        return side

    def _set_status(self, text: str, tone: str = "") -> None:
        """统一更新底部状态栏、侧边栏状态与顶栏徽标（三处保持一致）。

        Args:
            text: 状态文字（如「测速中……」「测速完成」）。
            tone: 语气 —— muted / success / warning / danger / accent；
                  留空时按文案关键词自动判定，避免每个调用点都手写语气。
        """
        if not tone:
            tone = self._infer_tone(text)
        colors = {
            "muted": theme.color("TEXT_MUTED"),
            "success": theme.color("GREEN"),
            "warning": theme.color("ORANGE"),
            "danger": theme.color("RED"),
            "accent": theme.color("ACCENT"),
        }
        color = colors.get(tone, theme.color("TEXT_MUTED"))
        if hasattr(self, "sidebar_status"):
            self.sidebar_status.setText(f"● {text}")
            self.sidebar_status.setStyleSheet(
                f"color: {color}; background: transparent; font-size: 12px;"
            )
        if hasattr(self, "topbar_status"):
            self.topbar_status.setText(f"● {text}")
            self.topbar_status.setStyleSheet(
                f"color: {color}; background: transparent; font-size: 12px;"
            )
        self.statusBar().showMessage(text)

    @staticmethod
    def _infer_tone(text: str) -> str:
        """按状态文案的关键词推断语气色（供 _set_status 使用）。

        Args:
            text: 状态文字。

        Returns:
            语气标识：danger / accent / warning / success / muted 之一。
        """
        if any(k in text for k in ("失败", "错误", "无法")):
            return "danger"
        if any(k in text for k in ("正在", "请稍候", "进行中")):
            return "accent"
        if any(k in text for k in ("没有可用", "已停止", "无有效")):
            return "warning"
        if any(k in text for k in ("完成", "已复制", "已保存", "可以点击")):
            return "success"
        return "muted"

    def _switch_view(self, key: str) -> None:
        """切换右侧显示的功能页面。

        Args:
            key: 页面标识 —— workbench / results / stability。
        """
        if not hasattr(self, "_pages") or key not in self._pages:
            return
        for name, page in self._pages.items():
            page.setVisible(name == key)
        for name, button in self._nav_buttons.items():
            button.setChecked(name == key)
        # 顶栏标题随视图变化
        titles = {
            "workbench": ("工作台", "导入候选 IP · 设置测速参数 · 开始测速"),
            "results": ("测试结果", "按综合评分排名 · 筛选 · 复制与导出"),
            "stability": ("稳定性复测", "对 TOP IP 多轮复测，取稳定者优先"),
            "sample": ("抽样测速", "CIDR 抽样 → 并发测速 → 生成可用节点"),
        }
        title, subtitle = titles.get(key, ("工作台", ""))
        self.page_title.setText(title)
        self.page_subtitle.setText(subtitle)
        self._active_view = key

        # 切到结果页时同步一次空态提示与按钮可用性
        # （否则「还没有测速结果」的提示可能在有数据时仍残留）
        if key == "results":
            self._sync_result_empty_state()

    def _sync_result_empty_state(self) -> None:
        """按当前是否有排名数据，同步结果页的空态提示与按钮可用性。"""
        if not hasattr(self, "result_empty_hint"):
            return
        entries = self.result_table.rank_entries
        self.result_empty_hint.setVisible(not entries)
        # 有数据时启用复制/导出（含节点按钮）
        self._set_export_buttons_enabled(bool(entries))

    # ------------------------------------------------------------------
    # 顶栏
    # ------------------------------------------------------------------
    def _build_topbar(self) -> QWidget:
        """构建顶栏：页面标题 + 副标题 + 右侧动作区。"""
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(10)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.page_title = QLabel("工作台")
        self.page_title.setObjectName("PageTitle")
        self.page_subtitle = QLabel("导入候选 IP · 设置测速参数 · 开始测速")
        self.page_subtitle.setObjectName("PageSubtitle")
        text_box.addWidget(self.page_title)
        text_box.addWidget(self.page_subtitle)
        layout.addLayout(text_box)
        layout.addStretch(1)

        # ---- 主题切换器（深色 / 浅色 / 跟随系统） ----
        self.theme_combo = QComboBox()
        self.theme_combo.setToolTip("切换界面主题（默认深色，仅本次运行内生效）")
        self.theme_combo.setMinimumWidth(104)
        for mode in theme.MODES:
            self.theme_combo.addItem(theme.MODE_LABELS[mode], mode)
        # 与 main.py 启动时应用的主题保持一致（默认深色）
        startup_mode = theme.load_saved_mode()
        default_index = next(
            (i for i, m in enumerate(theme.MODES) if m == startup_mode), 0
        )
        self.theme_combo.setCurrentIndex(default_index)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_selected)
        layout.addWidget(self.theme_combo)

        # 右上角常驻的总状态徽标
        self.topbar_status = QLabel("● 空闲")
        self.topbar_status.setObjectName("Muted")
        layout.addWidget(self.topbar_status)

        return bar

    def _on_theme_selected(self, index: int) -> None:
        """用户在顶栏切换主题：立即应用并记住选择。

        Args:
            index: 下拉框当前索引。
        """
        mode = self.theme_combo.itemData(index) or theme.DEFAULT_MODE
        self.apply_theme_mode(mode)
        self._set_status(f"主题已切换为「{theme.MODE_LABELS.get(mode, mode)}」", "muted")

    def apply_theme_mode(self, mode: str) -> str:
        """应用指定主题模式，并同步顶栏选择器的显示。

        供界面内切换与外部调用（如启动时恢复上次选择）共用，
        确保「下拉框显示」与「实际生效主题」始终一致。

        Args:
            mode: "dark" / "light" / "system"。

        Returns:
            实际生效的主题（"dark" 或 "light"）。
        """
        app = QApplication.instance()
        effective = mode
        if app is not None:
            effective = theme.apply_theme(app, mode)
            logger.info("应用主题：%s（实际生效 %s）", mode, effective)
            # 记住用户选择，下次启动沿用
            theme.save_mode(mode)

        # 同步下拉框显示（blockSignals 避免递归触发）
        if hasattr(self, "theme_combo"):
            target = next((i for i, m in enumerate(theme.MODES) if m == mode), 0)
            if self.theme_combo.currentIndex() != target:
                self.theme_combo.blockSignals(True)
                self.theme_combo.setCurrentIndex(target)
                self.theme_combo.blockSignals(False)

        # 主题切换后刷新表格单元格颜色（表格用 QColor 上色，不随 QSS 自动更新）
        if hasattr(self, "result_table"):
            self.result_table.reapply_colors()

        # 窗口自身底色跟着切（否则从深色切浅色时，窗口底色会残留旧值）
        self._apply_window_base_color()

        # 自绘标题栏跟着切（它用 QSS 上色，但样式表是在控件上单独设的）
        if hasattr(self, "title_bar"):
            self.title_bar.refresh_style()

        # 同步窗口标题栏（Windows 系统绘制，QSS 管不到，必须走原生 API）
        # 窗口尚未创建句柄时（如构造期）会安全返回 False，由 showEvent 兜底
        self._sync_titlebar_theme()
        return effective

    def _toggle_maximized(self) -> None:
        """最大化 / 还原窗口（自绘标题栏的按钮与双击都走这里）。

        ⚠️ **不能直接用 `showMaximized()`** —— 无边框窗口下 Qt 会按
        `screen.geometry()`（含任务栏区域）最大化，导致**窗口盖住任务栏**。
        正确做法是用 `availableGeometry()`（已扣除任务栏）手动设置几何。
        """
        if self.isMaximized():
            self.showNormal()
            # 还原到最大化前的尺寸与位置
            if self._normal_geometry is not None:
                self.setGeometry(self._normal_geometry)
        else:
            self._normal_geometry = self.geometry()
            screen = self.screen() or QApplication.primaryScreen()
            if screen is not None:
                self.setGeometry(screen.availableGeometry())
            else:
                self.showMaximized()
        self._sync_maximize_button()

    def _sync_maximize_button(self) -> None:
        """同步最大化按钮的图标与提示（含系统触发的最大化）。"""
        if hasattr(self, "title_bar"):
            self.title_bar.set_maximized(self.isMaximized())

    def changeEvent(self, event) -> None:  # noqa: N802（Qt 要求的驼峰命名）
        """窗口状态变化时同步最大化按钮（如系统贴边触发的最大化）。"""
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_maximize_button()

    def _sync_titlebar_theme(self) -> None:
        """让窗口标题栏颜色跟随当前主题（深色主题 ⇒ 深色标题栏）。

        背景：标题栏由 Windows 系统绘制，Qt 样式表**管不到**，
        深色主题下它会保持系统默认的白色，与黑灰面板形成刺眼色差。

        本方法只做「调用 + 记日志」，具体平台判断与异常保护都在
        `theme.apply_dark_titlebar` 内（非 Windows 平台自动跳过）。
        """
        ok = theme.apply_dark_titlebar(self)
        if ok and not getattr(self, "_titlebar_logged", False):
            # 只在首次成功时记一次日志，避免主题反复切换时刷屏
            self._titlebar_logged = True
            logger.info("已应用深色标题栏（Windows 原生 DWM）")

    def _apply_window_base_color(self) -> None:
        """把窗口自身的底色设成当前主题背景色，消除启动白闪。

        与 QSS 的分工：
        - QSS（`theme.build_qss`）负责**所有子控件**的样式，异步生效；
        - 本方法只设**顶层窗口**的调色板底色，构造期即生效 ⇒ show() 的第一帧
          就是深色，不再闪白。

        两处取的是同一个色值（`theme.color("BG_PRIMARY")`），不存在双真源。
        """
        try:
            pal = self.palette()
            pal.setColor(self.backgroundRole(), theme.qcolor("BG_PRIMARY"))
            self.setPalette(pal)
            # 让窗口用调色板底色填充背景（QMainWindow 默认不一定填）
            self.setAutoFillBackground(True)
        except Exception:
            # 底色是纯观感优化，失败不应影响启动
            pass

    def showEvent(self, event) -> None:  # noqa: N802（Qt 要求的驼峰命名）
        """窗口首次显示时同步标题栏 —— 此时窗口句柄才真正存在。

        为什么必须在这里补一次：`apply_theme_mode` 在启动流程中会被调用，
        但那个时刻窗口还没 show()，`winId()` 拿不到有效的 Windows 句柄，
        导致标题栏深色化失败（表现为「启动后标题栏仍是白色」）。
        """
        super().showEvent(event)
        self._sync_titlebar_theme()

    # ------------------------------------------------------------------
    # 统计卡片行（参照《API总代理》的 stats-grid）
    # ------------------------------------------------------------------
    def _build_stat_cards(self) -> None:
        """构建顶部四张统计卡片：候选 IP / 有效结果 / 最快速度 / 平均延迟。"""
        self.stat_cards: Dict[str, widgets.StatCard] = {}
        # 注意：图标必须用**单色 Unicode 符号**（▦ ✓ ◷ ≡ 等）。
        # 不要用 ⚡ ★ ♥ 这类「会触发 Windows 彩色 emoji 字体」的字符——
        # 它们会被渲染成彩色字形，无视 QSS 的 color 设置，破坏主题一致性。
        cards = (
            ("ip", "候选 IP", "0", "个", "▦", "ACCENT"),
            ("valid", "有效结果", "0", "条", "✓", "GREEN"),
            ("speed", "最快速度", "—", "", "≡", "ORANGE"),
            ("latency", "平均延迟", "—", "", "◷", "BLUE"),
        )
        self.stat_row = QWidget()
        row_layout = QHBoxLayout(self.stat_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)
        for key, label, value, unit, icon, color_key in cards:
            card = widgets.StatCard(label, value, unit, icon, color_key)
            self.stat_cards[key] = card
            row_layout.addWidget(card, 1)

    def _refresh_stat_cards(self) -> None:
        """根据当前数据刷新顶部统计卡片与结果空态提示。"""
        if not hasattr(self, "stat_cards"):
            return
        # 候选 IP：优先取 IP 面板里已导入/生成的数量
        try:
            ip_count = len(self.ip_panel.valid_entries)
        except Exception:
            ip_count = 0
        self.stat_cards["ip"].set_value(str(ip_count), "ACCENT")

        # 有效结果：当前排名条目数
        entries = self.result_table.rank_entries
        valid = [e for e in entries if e.score is not None]
        self.stat_cards["valid"].set_value(str(len(valid)), "GREEN")

        # 最快速度
        speeds = [e.result.download_speed_bps for e in valid if e.result.download_speed_bps]
        if speeds:
            self.stat_cards["speed"].set_value(f"{max(speeds) / 1048576:.2f}", "ORANGE")
        else:
            self.stat_cards["speed"].set_value("—", "TEXT_MUTED")

        # 平均 TCP 延迟
        latencies = [e.result.latency for e in valid if e.result.latency is not None]
        if latencies:
            self.stat_cards["latency"].set_value(f"{sum(latencies) / len(latencies):.0f}", "BLUE")
        else:
            self.stat_cards["latency"].set_value("—", "TEXT_MUTED")

        # 结果空态提示：有结果就收起来
        if hasattr(self, "result_empty_hint"):
            self.result_empty_hint.setVisible(not entries)

        # 工作台流程引导条随数据状态同步
        self._refresh_guide()

    # ------------------------------------------------------------------
    # 页面 1：工作台（IP 来源 + 测速设置 + 测速进度）
    # ------------------------------------------------------------------
    def _build_workbench_page(self) -> QWidget:
        """构建工作台页面：流程引导 + IP 来源面板 + 测速设置 + 测试进度。"""
        page = QWidget()
        page.setObjectName("PageContainer")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_guide_bar())
        layout.addWidget(self.stat_row)
        layout.addWidget(self._build_ip_panel_card())
        layout.addWidget(self._build_setting_group())
        layout.addWidget(self._build_progress_group())
        return page

    def _build_guide_bar(self) -> QWidget:
        """工作台顶部的流程引导条：告诉用户现在该做哪一步。

        新用户最容易卡在「打开后不知道先干什么」，这里用三步骤可视化
        当前进度，并随数据状态自动高亮当前应做的一步。
        """
        panel = widgets.Panel("使用流程", "三步完成优选")
        body = panel.body_layout

        row = QHBoxLayout()
        row.setSpacing(10)
        self.guide_labels: Dict[str, QLabel] = {}
        steps = (
            ("ip", "① 导入候选 IP", "从文件/粘贴/自动获取三种方式任选"),
            ("scan", "② 开始测速", "按当前参数测试延迟与速度"),
            ("result", "③ 查看与导出", "到「测试结果」复制或导出节点"),
        )
        for key, title, desc in steps:
            cell = QWidget()
            cell_layout = QVBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("Secondary")
            t.setStyleSheet(
                f"color: {theme.color('TEXT_MUTED')}; font-size: 13px; font-weight: bold;"
                "background: transparent;"
            )
            d = widgets.hint_label(desc, "muted")
            d.setWordWrap(False)
            cell_layout.addWidget(t)
            cell_layout.addWidget(d)
            self.guide_labels[key] = t
            row.addWidget(cell, 1)
        body.addLayout(row)

        self.guide_hint = widgets.hint_label(
            "第 ① 步：请先导入候选 IP（上方「IP 来源」区域）", "accent"
        )
        body.addWidget(self.guide_hint)
        self._guide_panel = panel
        return panel

    def _refresh_guide(self) -> None:
        """按当前数据状态刷新流程引导条的高亮与提示文案。"""
        if not hasattr(self, "guide_labels"):
            return
        has_ips = bool(self._valid_entries)
        has_results = bool(self.result_table.rank_entries)
        has_final = bool(self.result_table.final_entries)

        active = "result" if has_results else ("scan" if has_ips else "ip")
        for key, label in self.guide_labels.items():
            is_active = key == active
            color = theme.color("ACCENT") if is_active else theme.color("TEXT_MUTED")
            label.setStyleSheet(
                f"color: {color}; font-size: 13px; font-weight: bold;"
                "background: transparent;"
            )

        if active == "ip":
            text = "第 ① 步：请先导入候选 IP（下方「IP 来源」区域，可粘贴或自动获取）"
        elif active == "scan":
            count = len(self._valid_entries)
            text = f"第 ② 步：已导入 {count} 个 IP，点【开始测速】即可"
        else:
            if has_final:
                text = "第 ③ 步：测速与复测已完成，到「测试结果」复制或导出节点"
            else:
                text = "第 ③ 步：测速完成，到「测试结果」查看排名；如需更稳的节点可先做「稳定性复测」"
        self.guide_hint.setText(text)

    def _build_ip_panel_card(self) -> QWidget:
        """把 IP 来源面板包进黑灰主题的卡片容器里。"""
        panel = widgets.Panel("IP 来源", "导入文件 / 粘贴 / 从 Cloudflare 自动获取")
        self.ip_panel = IPPanel()
        self.ip_panel.imported.connect(self._on_ips_imported)
        self.ip_panel.cleared.connect(self._on_ips_cleared)
        self.ip_panel.fetch_completed.connect(self._on_fetch_completed)
        self.ip_panel.fetch_failed.connect(self._on_fetch_failed)
        # IPPanel 自带 GroupBox 外框，这里去掉它的标题与边框，融进外层卡片
        self.ip_panel.setTitle("")
        self.ip_panel.setStyleSheet("QGroupBox { border: none; background: transparent; padding: 0; }")
        panel.body_layout.addWidget(self.ip_panel)
        return panel

    # ------------------------------------------------------------------
    # 页面 2：测试结果
    # ------------------------------------------------------------------
    def _build_results_page(self) -> QWidget:
        """构建测试结果页面（表格 + 筛选 + 复制导出）。"""
        page = QWidget()
        page.setObjectName("PageContainer")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_result_group())
        return page

    # ------------------------------------------------------------------
    # 页面 3：稳定性复测
    # ------------------------------------------------------------------
    def _build_stability_page(self) -> QWidget:
        """构建稳定性复测页面。"""
        page = QWidget()
        page.setObjectName("PageContainer")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.addWidget(self._build_stability_group())
        return page


    def _build_setting_group(self) -> QGroupBox:
        """测速设置区域（V1.2：新增 HTTP 测试与下载测速的设置）。

        V2.0 界面重构：外观改为黑灰主题卡片，控件对象与信号连接保持不变。
        """
        group = QGroupBox("测速设置")
        layout = QHBoxLayout(group)
        layout.setSpacing(28)

        # ---- 左半部分：第一级 TCP 测试设置（保持第一阶段原样） ----
        tcp_form = QFormLayout()
        tcp_form.setSpacing(10)
        tcp_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(MIN_CONCURRENCY, MAX_CONCURRENCY)
        self.concurrency_spin.setValue(DEFAULT_CONCURRENCY)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(MIN_TIMEOUT_MS, MAX_TIMEOUT_MS)
        self.timeout_spin.setValue(DEFAULT_TIMEOUT_MS)
        self.timeout_spin.setSuffix(" ms")
        tcp_form.addRow("端口：", self.port_spin)
        tcp_form.addRow("并发：", self.concurrency_spin)
        tcp_form.addRow("TCP超时：", self.timeout_spin)
        layout.addLayout(tcp_form)

        # ---- 右半部分：第二级 HTTP + 第三级 下载（V1.2 新增） ----
        stage_form = QFormLayout()
        stage_form.setSpacing(10)
        stage_form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        # HTTP 测试开关（TCP 成功后才执行）
        self.http_checkbox = QCheckBox("启用 HTTP 测试")
        self.http_checkbox.setChecked(True)
        self.http_checkbox.setToolTip("TCP 连接成功后，再测试 HTTP/HTTPS 是否真的能通")
        self.http_checkbox.toggled.connect(self._on_http_toggled)

        self.http_timeout_spin = QSpinBox()
        self.http_timeout_spin.setRange(MIN_HTTP_TIMEOUT_MS, MAX_HTTP_TIMEOUT_MS)
        self.http_timeout_spin.setValue(DEFAULT_HTTP_TIMEOUT_MS)
        self.http_timeout_spin.setSuffix(" ms")

        # 下载测速开关（HTTP 成功后才执行）
        self.download_checkbox = QCheckBox("启用下载测速")
        self.download_checkbox.setChecked(True)
        self.download_checkbox.setToolTip("HTTP 测试成功后，再下载一小段数据来测量真实速度")
        self.download_checkbox.toggled.connect(self._on_download_toggled)

        self.download_size_combo = QComboBox()
        for text, size in DOWNLOAD_SIZE_OPTIONS:
            self.download_size_combo.addItem(text, size)
        # 默认选中 1 MB
        default_index = next(
            (
                index
                for index, (_, size) in enumerate(DOWNLOAD_SIZE_OPTIONS)
                if size == DEFAULT_DOWNLOAD_BYTES
            ),
            2,
        )
        self.download_size_combo.setCurrentIndex(default_index)

        self.download_timeout_spin = QSpinBox()
        self.download_timeout_spin.setRange(MIN_DOWNLOAD_TIMEOUT_MS, MAX_DOWNLOAD_TIMEOUT_MS)
        self.download_timeout_spin.setValue(DEFAULT_DOWNLOAD_TIMEOUT_MS)
        self.download_timeout_spin.setSuffix(" ms")

        stage_form.addRow(self.http_checkbox)
        stage_form.addRow("HTTP超时：", self.http_timeout_spin)
        stage_form.addRow(self.download_checkbox)
        stage_form.addRow("下载大小：", self.download_size_combo)
        stage_form.addRow("下载超时：", self.download_timeout_spin)
        layout.addLayout(stage_form)

        button_layout = QVBoxLayout()
        button_layout.setSpacing(8)
        self.start_button = widgets.primary_button("开始测速", "按当前设置开始三级测速")
        self.start_button.setMinimumHeight(38)
        self.start_button.clicked.connect(self._on_start_scan)
        self.stop_button = widgets.danger_button("停止测速", "立即停止本轮测速（已完成的结果会保留）")
        self.stop_button.setMinimumHeight(38)
        self.stop_button.clicked.connect(self._on_stop_scan)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)

        layout.addStretch(1)

        # 根据开关的初始状态，同步子控件的可用性
        self._on_http_toggled(self.http_checkbox.isChecked())
        self._on_download_toggled(self.download_checkbox.isChecked())
        return group

    def _on_http_toggled(self, checked: bool) -> None:
        """HTTP 开关变化：联动 HTTP 超时输入框。"""
        # 测速/复测进行中不允许改动设置；关闭 HTTP 测试时，下载测速也一定不会执行
        editable = checked and not self._running and not self._stability_running
        self.http_timeout_spin.setEnabled(editable)
        self.download_checkbox.setEnabled(checked and not self._running and not self._stability_running)
        self._on_download_toggled(self.download_checkbox.isChecked())

    def _on_download_toggled(self, checked: bool) -> None:
        """下载开关变化：联动下载大小和超时输入框。"""
        enabled = (
            checked and self.http_checkbox.isChecked()
            and not self._running and not self._stability_running
        )
        self.download_size_combo.setEnabled(enabled)
        self.download_timeout_spin.setEnabled(enabled)

    def _build_progress_group(self) -> QGroupBox:
        """测试进度区域。"""
        group = QGroupBox("测试进度")
        layout = QVBoxLayout(group)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("%p%")
        layout.addWidget(self.progress_bar)

        info_layout = QHBoxLayout()
        self.tested_label = QLabel("已测试：0 / 0")
        self.success_label = QLabel("成功：0")
        self.failed_label = QLabel("失败：0")
        self.elapsed_label = QLabel("用时：0.0 秒")
        for label in (self.tested_label, self.success_label, self.failed_label, self.elapsed_label):
            info_layout.addWidget(label)
        info_layout.addStretch(1)
        layout.addLayout(info_layout)

        # ---- V1.2 新增：三级测试各自的成功 / 失败统计 ----
        stage_layout = QHBoxLayout()
        self.stage_label = QLabel("阶段统计：")
        self.tcp_stat_label = QLabel("TCP 成功 0 / 失败 0")
        self.http_stat_label = QLabel("HTTP 成功 0 / 失败 0 / 未测试 0")
        self.download_stat_label = QLabel("下载 成功 0 / 失败 0 / 未测试 0")
        for label in (
            self.stage_label,
            self.tcp_stat_label,
            self.http_stat_label,
            self.download_stat_label,
        ):
            stage_layout.addWidget(label)
        stage_layout.addStretch(1)
        layout.addLayout(stage_layout)

        return group

    # ==================================================================
    # V1.4：稳定性复测（对 V1.3 TOP IP 多次重复测试，算稳定性评分与最终排名）
    # ==================================================================
    def _build_stability_group(self) -> QGroupBox:
        """稳定性复测区域：复测轮数/并发选择、开始/停止按钮、进度与当前状态。

        只在主测速结束且有 V1.3 排名后才允许开始（按钮禁用逻辑见
        _set_running_state / _on_scan_finished）。
        """
        group = QGroupBox("复测设置")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # ---- 选项行：复测轮数 + 复测并发 ----
        option_layout = QHBoxLayout()
        option_layout.addWidget(QLabel("复测轮数："))
        self.stab_rounds_combo = QComboBox()
        for n in STABILITY_ROUND_OPTIONS:
            self.stab_rounds_combo.addItem(f"{n} 次", n)
        default_round_index = next(
            (i for i, n in enumerate(STABILITY_ROUND_OPTIONS) if n == DEFAULT_STABILITY_ROUNDS),
            1,
        )
        self.stab_rounds_combo.setCurrentIndex(default_round_index)
        self.stab_rounds_combo.setToolTip("同一个 TOP IP 集合重复测试几次（次数越多结论越稳，但用时越长）")
        option_layout.addWidget(self.stab_rounds_combo)

        option_layout.addWidget(QLabel("复测并发："))
        self.stab_concurrency_combo = QComboBox()
        for n in STABILITY_CONCURRENCY_OPTIONS:
            self.stab_concurrency_combo.addItem(str(n), n)
        default_conc_index = next(
            (i for i, n in enumerate(STABILITY_CONCURRENCY_OPTIONS)
             if n == DEFAULT_STABILITY_CONCURRENCY),
            1,
        )
        self.stab_concurrency_combo.setCurrentIndex(default_conc_index)
        self.stab_concurrency_combo.setToolTip("复测时同时测试几个 IP（越大越快，但对网络压力越大）")
        option_layout.addWidget(self.stab_concurrency_combo)

        # ---- 开始 / 停止按钮 ----
        self.stab_start_button = widgets.primary_button(
            "开始复测", "对当前 V1.3 排名的 TOP IP 进行多轮复测"
        )
        self.stab_start_button.clicked.connect(self._on_stability_start)
        self.stab_start_button.setEnabled(False)  # 主测速结束前不可用
        option_layout.addWidget(self.stab_start_button)

        self.stab_stop_button = widgets.danger_button(
            "停止复测", "停止复测（已完成的轮次结果会保留）"
        )
        self.stab_stop_button.clicked.connect(self._on_stability_stop)
        self.stab_stop_button.setEnabled(False)  # 复测进行中才可用
        option_layout.addWidget(self.stab_stop_button)
        option_layout.addStretch(1)
        layout.addLayout(option_layout)

        # ---- 进度条 ----
        self.stab_progress_bar = QProgressBar()
        self.stab_progress_bar.setRange(0, 100)
        self.stab_progress_bar.setValue(0)
        self.stab_progress_bar.setFormat("%p%")
        layout.addWidget(self.stab_progress_bar)

        # ---- 状态行：当前轮次/当前IP/统计 ----
        status_layout = QHBoxLayout()
        self.stab_status_label = QLabel("尚未复测")
        self.stab_current_label = QLabel("当前：--")
        self.stab_summary_label = QLabel("")
        # 摘要可能很长（稳定数/平均稳定性/TOP10），允许自动换行避免撑宽窗口
        self.stab_summary_label.setWordWrap(True)
        for label in (self.stab_status_label, self.stab_current_label, self.stab_summary_label):
            status_layout.addWidget(label)
        status_layout.addStretch(1)
        layout.addLayout(status_layout)

        # ---- 稳定结果导出按钮行 ----
        export_layout = QHBoxLayout()
        export_layout.setSpacing(8)
        self.export_stable_txt_button = widgets.ghost_button(
            "导出稳定TOP TXT", "导出最终排名前 100 的 IP（每行一个）到 output\\ 目录"
        )
        self.export_stable_txt_button.clicked.connect(self._on_export_stable_txt)
        self.export_stable_txt_button.setEnabled(False)  # 复测完成后才有数据
        export_layout.addWidget(self.export_stable_txt_button)

        self.export_stable_csv_button = widgets.ghost_button(
            "导出稳定性CSV", "导出稳定性复测的完整统计（含稳定性/最终评分）到 output\\ 目录"
        )
        self.export_stable_csv_button.clicked.connect(self._on_export_stable_csv)
        self.export_stable_csv_button.setEnabled(False)  # 复测完成后才有数据
        export_layout.addWidget(self.export_stable_csv_button)
        export_layout.addStretch(1)
        layout.addLayout(export_layout)

        return group


    def _build_result_group(self) -> QGroupBox:
        """测试结果区域（V1.3：排名/评分/筛选/复制/导出）。

        V2.0 界面重构：外观改为黑灰主题卡片，控件对象与信号连接保持不变。
        """
        group = QGroupBox("排名与筛选")
        layout = QVBoxLayout(group)
        layout.setSpacing(12)

        # ---- V1.3 新增：筛选与 TOP 设置行 ----
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("最低速度："))
        self.speed_filter_combo = QComboBox()
        for text, _value in SPEED_FILTER_OPTIONS:
            self.speed_filter_combo.addItem(text)
        self.speed_filter_combo.setToolTip("只有下载速度不低于该值的 IP 才进入最终排名")
        filter_layout.addWidget(self.speed_filter_combo)

        filter_layout.addWidget(QLabel("最大TCP延迟："))
        self.latency_filter_combo = QComboBox()
        for text, _value in LATENCY_FILTER_OPTIONS:
            self.latency_filter_combo.addItem(text)
        self.latency_filter_combo.setToolTip("只有 TCP 延迟不超过该值的 IP 才进入最终排名")
        filter_layout.addWidget(self.latency_filter_combo)

        filter_layout.addWidget(QLabel("显示："))
        self.top_combo = QComboBox()
        for n in TOP_OPTIONS:
            self.top_combo.addItem(f"TOP {n}", n)
        # 默认选中 TOP 100
        default_top_index = next(
            (i for i, n in enumerate(TOP_OPTIONS) if n == DEFAULT_TOP_N), len(TOP_OPTIONS) - 1
        )
        self.top_combo.setCurrentIndex(default_top_index)
        filter_layout.addWidget(self.top_combo)

        self.apply_filter_button = QPushButton("应用筛选")
        self.apply_filter_button.setToolTip("按上面的条件重新计算排名（测速结束后可用）")
        self.apply_filter_button.clicked.connect(self._apply_ranking_from_ui)
        filter_layout.addWidget(self.apply_filter_button)

        # 列显示切换：默认只显示核心列（避免 17 列挤压需横向滚动）
        self.column_toggle_button = widgets.ghost_button(
            "显示全部列",
            "切换显示全部 17 列（含稳定性明细）；默认只显示核心列，避免横向滚动",
        )
        self.column_toggle_button.setCheckable(True)
        self.column_toggle_button.toggled.connect(self._on_toggle_columns)
        filter_layout.addWidget(self.column_toggle_button)

        filter_layout.addStretch(1)
        layout.addLayout(filter_layout)

        self.result_table = ResultTable()
        layout.addWidget(self.result_table)

        # 空态提示：表格无数据时给出「下一步做什么」，有数据后自动隐藏
        self.result_empty_hint = widgets.hint_label(
            "还没有测速结果 —— 请先到「工作台」导入 IP 并点击【开始测速】。", "muted"
        )
        self.result_empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.result_empty_hint)

        # ---- 代理模板（把优选 IP 直接变成可用节点链接） ----
        template_row = QHBoxLayout()
        template_row.setSpacing(8)
        template_label = QLabel("代理模板：")
        template_label.setObjectName("Secondary")
        template_row.addWidget(template_label)
        self.result_template_edit = QLineEdit()
        self.result_template_edit.setPlaceholderText(
            "粘贴你的节点模板，含 @IP:端口 即可自动替换（例如 vless://uuid@1.2.3.4:443?type=ws&host=你的域名）"
        )
        self.result_template_edit.setToolTip(
            "测速得到的优选 IP 会替换掉模板里的 @IP:端口，生成可直接导入 V2RayN 的节点链接"
        )
        self.result_template_edit.textChanged.connect(self._on_result_template_changed)
        template_row.addWidget(self.result_template_edit, 1)
        layout.addLayout(template_row)

        # 模板状态提示（未填时说明用途，填了则显示识别结果）
        self.result_template_hint = widgets.hint_label(
            "提示：填入模板后即可「复制节点」或「导出节点」，把优选 IP 变成可直接使用的节点链接",
            "muted",
        )
        layout.addWidget(self.result_template_hint)

        # ---- V1.3 新增：复制与导出按钮行 ----
        button_layout = QHBoxLayout()
        self.copy_top10_button = QPushButton("复制TOP10")
        self.copy_top50_button = QPushButton("复制TOP50")
        self.copy_top100_button = QPushButton("复制TOP100")
        self.export_txt_button = QPushButton("导出TXT")
        self.export_csv_button = QPushButton("导出CSV")
        for n, button in ((10, self.copy_top10_button), (50, self.copy_top50_button), (100, self.copy_top100_button)):
            button.setToolTip(f"复制前 {n} 名 IP（每行一个，不带其他文字）")
            button.clicked.connect(lambda _checked=False, count=n: self._copy_top(count))
        self.export_txt_button.setToolTip("导出 TOP100 的 IP 列表（会弹出保存位置选择）")
        self.export_csv_button.setToolTip("导出完整结果（含排名/延迟/状态/评分），会弹出保存位置选择")
        self.export_txt_button.clicked.connect(self._on_export_txt)
        self.export_csv_button.clicked.connect(self._on_export_csv)
        for button in (
            self.copy_top10_button, self.copy_top50_button, self.copy_top100_button,
            self.export_txt_button, self.export_csv_button,
        ):
            button.setEnabled(False)  # 测速结束后才有数据
            button_layout.addWidget(button)
        button_layout.addStretch(1)
        layout.addLayout(button_layout)

        # ---- 节点操作行（依赖代理模板） ----
        node_layout = QHBoxLayout()
        node_layout.setSpacing(8)
        self.copy_selected_button = widgets.ghost_button(
            "复制选中行", "只复制你在表格里选中的行（按住 Ctrl/Shift 可多选）"
        )
        self.copy_selected_button.clicked.connect(self._on_copy_selected)
        self.export_selected_button = widgets.ghost_button(
            "导出选中行", "只把你在表格里选中的行导出为 CSV（会弹出保存位置选择）"
        )
        self.export_selected_button.clicked.connect(self._on_export_selected)
        self.copy_nodes_button = widgets.primary_button(
            "复制节点", "把优选 IP 套进模板生成节点链接，复制到剪贴板（可直接在 V2RayN 从剪贴板导入）"
        )
        self.copy_nodes_button.clicked.connect(self._on_copy_nodes)
        self.export_nodes_button = widgets.ghost_button(
            "导出节点", "把节点链接保存为 txt（会弹出保存位置选择）"
        )
        self.export_nodes_button.clicked.connect(self._on_export_nodes)
        for button in (
            self.copy_selected_button, self.export_selected_button,
            self.copy_nodes_button, self.export_nodes_button,
        ):
            button.setEnabled(False)  # 测速结束后才有数据
            node_layout.addWidget(button)
        node_layout.addStretch(1)
        layout.addLayout(node_layout)

        self.result_summary_label = QLabel("")
        self.result_summary_label.setObjectName("Secondary")
        self.result_summary_label.setWordWrap(True)
        layout.addWidget(self.result_summary_label)

        return group

    def _on_toggle_columns(self, show_all: bool) -> None:
        """切换结果表格的列显示（核心列 / 全部列）。

        Args:
            show_all: 是否显示全部列。
        """
        self.result_table.set_show_all_columns(show_all)
        self.column_toggle_button.setText("只显示核心列" if show_all else "显示全部列")
        count = self.result_table.visible_columns_count()
        self._set_status(f"结果表格当前显示 {count} 列", "muted")

    def _on_result_template_changed(self) -> None:
        """结果页模板变化：校验并给出即时反馈。"""
        from core.sampler import extract_template_port

        text = self.result_template_edit.text()
        if not text.strip():
            self.result_template_hint.setObjectName("Muted")
            self.result_template_hint.setText(
                "提示：填入模板后即可「复制节点」或「导出节点」，把优选 IP 变成可直接使用的节点链接"
            )
        else:
            parsed = extract_template_port(text)
            if parsed:
                self.result_template_hint.setObjectName("Success")
                self.result_template_hint.setText(
                    f"已识别端点：@{'{ip}'}:{parsed[0]}（导出时会替换为优选 IP 与实测端口）"
                )
            else:
                self.result_template_hint.setObjectName("Warning")
                self.result_template_hint.setText(
                    "⚠ 模板中未找到 @IP:端口 格式，无法生成节点"
                )
        self.result_template_hint.style().unpolish(self.result_template_hint)
        self.result_template_hint.style().polish(self.result_template_hint)

    def _result_nodes(self) -> List[str]:
        """按当前模板与排名生成节点链接列表。"""
        from utils.export import ExportError, build_nodes_from_entries

        template = self.result_template_edit.text().strip()
        if not template:
            return []
        try:
            return build_nodes_from_entries(
                self.result_table.rank_entries, template, top_n=DEFAULT_TOP_N
            )
        except ExportError:
            return []

    def _on_copy_selected(self) -> None:
        """复制用户在表格里选中的行（IP 或节点，取决于是否填了模板）。

        有模板时复制节点链接，否则复制纯 IP —— 与用户此时的目的相符。
        """
        ips = self.result_table.selected_ips()
        if not ips:
            QMessageBox.information(
                self, "没有选中行",
                "请先在下方表格里选中若干行（按住 Ctrl 或 Shift 可多选），再点【复制选中行】。",
            )
            return

        template = self.result_template_edit.text().strip()
        if template:
            # 有模板 → 生成节点（只针对选中的行）
            from utils.export import ExportError, build_nodes_from_entries

            selected = [
                e for e in self.result_table.rank_entries if e.result.ip in set(ips)
            ]
            if not selected:
                # 排名表里找不到（例如表格显示的是原始结果），退化为直接套模板
                from core.sampler import build_node, extract_template_port

                parsed = extract_template_port(template)
                if parsed is None:
                    QMessageBox.warning(self, "模板格式有误", "模板中未找到 @IP:端口 格式。")
                    return
                _, pair = parsed
                nodes = [
                    build_node(template, ip, self._find_port_by_ip(ip), pair) for ip in ips
                ]
            else:
                try:
                    nodes = build_nodes_from_entries(selected, template, top_n=len(selected))
                except ExportError as exc:
                    QMessageBox.warning(self, "模板格式有误", str(exc))
                    return
            QApplication.clipboard().setText("\n".join(nodes))
            self._set_status(f"已复制选中的 {len(nodes)} 条节点到剪贴板", "success")
            logger.info("用户复制选中节点：%s 条", len(nodes))
        else:
            QApplication.clipboard().setText("\n".join(ips))
            self._set_status(f"已复制选中的 {len(ips)} 个 IP 到剪贴板", "success")
            logger.info("用户复制选中 IP：%s 个", len(ips))

    def _find_port_by_ip(self, ip: str) -> int:
        """按 IP 查其实测端口（查不到时回退 443）。

        Args:
            ip: 目标 IP。

        Returns:
            端口号。
        """
        for entry in self.result_table.rank_entries:
            if entry.result.ip == ip:
                return entry.result.port
        for entry in self.result_table.results:
            if entry.ip == ip:
                return entry.port
        return 443

    def _on_copy_nodes(self) -> None:
        """复制节点链接到剪贴板。"""
        if not self.result_template_edit.text().strip():
            QMessageBox.information(
                self, "请先填写代理模板",
                "要生成节点链接，需要先在上方「代理模板」里填入你自己的节点模板。\n\n"
                "模板需包含 @IP:端口 片段，例如：\n"
                "vless://你的UUID@1.2.3.4:443?encryption=none&security=none&type=ws&host=你的域名",
            )
            return
        nodes = self._result_nodes()
        if not nodes:
            QMessageBox.information(
                self, "没有可导出的节点",
                "当前没有测速成功的 IP，请先完成测速；或检查代理模板是否含 @IP:端口。",
            )
            return
        QApplication.clipboard().setText("\n".join(nodes))
        self._set_status(f"已复制 {len(nodes)} 条节点到剪贴板，可在 V2RayN 从剪贴板导入", "success")
        logger.info("用户复制节点：%s 条", len(nodes))

    def _on_export_nodes(self) -> None:
        """导出节点链接（弹出另存为对话框）。"""
        if not self.result_template_edit.text().strip():
            QMessageBox.information(
                self, "请先填写代理模板",
                "要导出节点链接，需要先在上方「代理模板」里填入你自己的节点模板。",
            )
            return
        nodes = self._result_nodes()
        if not nodes:
            QMessageBox.information(
                self, "没有可导出的节点",
                "当前没有测速成功的 IP，请先完成测速；或检查代理模板是否含 @IP:端口。",
            )
            return

        default_path = str(
            data_root() / "output" / f"优选节点_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "保存节点链接", default_path, "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            from utils.export import export_nodes

            saved = export_nodes(
                self.result_table.rank_entries,
                self.result_template_edit.text().strip(),
                top_n=DEFAULT_TOP_N,
                target=Path(path),
            )
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            logger.error("导出节点失败：%s", exc)
            return
        self._set_status(f"已导出 {len(nodes)} 条节点到 {saved}", "success")
        QMessageBox.information(self, "导出成功", f"已导出 {len(nodes)} 条节点：\n{saved}")

    def _copy_top(self, count: int) -> None:
        """复制前 N 名 IP 到剪贴板（每行一个，不带其他文字）。

        V1.4：复测完成后优先按最终排名复制（稳定者优先），
        否则按 V1.3 排名复制（见 ResultTable.top_ips）。
        """
        ips = self.result_table.top_ips(count)
        if not ips:
            QMessageBox.information(self, "提示", "还没有可复制的 IP，请先完成测速。")
            return
        QApplication.clipboard().setText("\n".join(ips))
        self._set_status(f"已复制 TOP{len(ips)} 共 {len(ips)} 个 IP 到剪贴板")
        logger.info("用户复制 TOP%s：%s 个 IP", count, len(ips))

    def _on_export_txt(self) -> None:
        """导出 TXT（V1.3 排名 TOP100，每行一个 IP）。

        会先弹出「另存为」让用户选保存位置；不选则取消。

        V1.4：想要「按最终排名（稳定者优先）」的列表请用稳定性区域的
        【导出稳定TOP TXT】按钮（见 _on_export_stable_txt）。
        """
        entries = self.result_table.rank_entries
        valid = [e for e in entries if e.score is not None]
        if not valid:
            QMessageBox.information(self, "没有可导出的内容", "请先完成测速。")
            return

        content = "\n".join(e.result.ip for e in valid[:DEFAULT_TOP_N]) + "\n"
        default_path = str(
            data_root() / "output" / f"IP优选_TOP{DEFAULT_TOP_N}_{datetime.now():%Y%m%d_%H%M%S}.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 IP 列表", default_path, "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            saved = export_plain_text(content, Path(path))
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self._set_status(f"已导出 TOP{DEFAULT_TOP_N} IP 列表到 {saved}", "success")
        QMessageBox.information(self, "导出成功", f"TOP TXT 已保存到：\n{saved}")
        logger.info("用户导出 TOP TXT：%s", saved)

    def _on_export_csv(self) -> None:
        """导出 CSV（V1.3 完整字段）。

        会先弹出「另存为」让用户选保存位置；不选则取消。

        V1.4：想要含稳定性/最终评分的完整统计请用稳定性区域的
        【导出稳定性CSV】按钮（见 _on_export_stable_csv）。

        2026-10-09 收敛：此前本方法**自己手写了一遍 CSV 字段与格式化**，
        与 utils/export.export_csv 构成双真源（速度格式化 `/1048576:.3f`
        vs `_format_speed_mbps`、状态列文案也不一致）。现统一委托给
        export_csv，GUI 只负责「取数据 + 问路径」。
        """
        entries = self.result_table.rank_entries
        if not entries:
            QMessageBox.information(self, "没有可导出的内容", "请先完成测速。")
            return

        default_path = str(
            data_root() / "output" / f"IP优选_结果_{datetime.now():%Y%m%d_%H%M%S}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "保存测速结果", default_path, "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            saved = export_csv(list(entries), target=Path(path))
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self._set_status(f"已导出 {len(entries)} 行结果到 {saved}", "success")
        QMessageBox.information(self, "导出成功", f"CSV 已保存到：\n{saved}")
        logger.info("用户导出 CSV：%s", saved)

    def _on_export_selected(self) -> None:
        """导出用户在表格里选中的行到 CSV。

        与【复制选中行】成对：复制走剪贴板，本方法走文件。

        此前只有「复制选中行」没有「导出选中行」—— 用户挑出几个 IP
        想要文件时，只能全量导出再手工删。本方法补上这个缺口。

        行为：
        - 未选中任何行 → 提示并返回（不弹保存框，避免空操作）；
        - 选中的 IP 在当前快照里找不到（例如表格显示的是原始结果而非排名）
          → 用 IP 直接构造只含基础字段的行，保证「选了什么就导出什么」；
        - 导出顺序与表格显示顺序一致。
        """
        ips = self.result_table.selected_ips()
        if not ips:
            QMessageBox.information(
                self, "没有选中行",
                "请先在下方表格里选中若干行（按住 Ctrl 或 Shift 可多选），再点【导出选中行】。",
            )
            return

        wanted = set(ips)
        # 优先用最终排名（含稳定性字段），其次用 V1.3 排名，保持与表格显示一致
        entries = [
            e for e in (self.result_table.final_entries or self.result_table.rank_entries)
            if e.result.ip in wanted
        ]
        if not entries:
            QMessageBox.warning(
                self, "无法导出选中行",
                "选中的行不在当前排名快照里，请先完成测速或改用【导出CSV】。",
            )
            return

        default_path = str(
            data_root() / "output" / f"IP优选_选中{len(entries)}条_{datetime.now():%Y%m%d_%H%M%S}.csv"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "保存选中的结果", default_path, "CSV 文件 (*.csv);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            saved = export_csv(entries, target=Path(path), filename_prefix="IP优选_选中")
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        self._set_status(f"已导出选中的 {len(entries)} 行到 {saved}", "success")
        QMessageBox.information(self, "导出成功", f"已导出 {len(entries)} 行到：\n{saved}")
        logger.info("用户导出选中行：%s 行 → %s", len(entries), saved)

    # ------------------------------------------------------------------
    # V1.3：评分 / 排名 / 筛选 / 摘要
    # ------------------------------------------------------------------
    def _current_filters(self) -> dict:
        """读取界面上的筛选条件。"""
        speed_text = self.speed_filter_combo.currentText()
        latency_text = self.latency_filter_combo.currentText()
        min_speed_bps = next((v for t, v in SPEED_FILTER_OPTIONS if t == speed_text), None)
        max_latency = next((v for t, v in LATENCY_FILTER_OPTIONS if t == latency_text), None)
        return {"min_speed_bps": min_speed_bps, "max_tcp_latency_ms": max_latency}

    def _apply_ranking_from_ui(self) -> None:
        """按界面筛选条件重建排名（需要已经完成过测速）。"""
        if not self._all_results:
            QMessageBox.information(self, "提示", "还没有测速结果，请先完成一次测速。")
            return
        self._refresh_ranking_view()

    def _refresh_ranking_view(self) -> None:
        """用当前筛选条件重新评分排名，并刷新表格与摘要。"""
        filters = self._current_filters()
        top_n = self.top_combo.currentData() or DEFAULT_TOP_N
        entries = build_ranking(
            self._all_results,
            min_speed_bps=filters["min_speed_bps"],
            max_tcp_latency_ms=filters["max_tcp_latency_ms"],
            top_n=top_n,
        )
        self.result_table.set_ranking(entries)
        self.result_table.enable_sorting()
        self._update_summary_text(entries)
        self._refresh_stat_cards()
        # V1.4：V1.3 排名一旦变化，旧的最终排名与复测汇总即失效
        # （result_table.set_ranking 已清空最终排名快照，这里同步清空复测汇总）
        self._stability_map = {}
        self._stab_results_all = []
        self.export_stable_txt_button.setEnabled(False)
        self.export_stable_csv_button.setEnabled(False)
        self.stab_status_label.setText("尚未复测")
        self.stab_summary_label.setText("")
        self._refresh_stability_controls()

    def _update_summary_text(self, entries) -> None:
        """刷新结果摘要（含最快/平均速度、最低/平均延迟、TOP1）。"""
        valid = [e for e in entries if e.score is not None]
        if not valid:
            self.result_summary_label.setText("没有满足筛选条件的有效 IP —— 可放宽上方筛选条件后点击【应用筛选】重试。")
            return
        speeds = [e.result.download_speed_bps for e in valid if e.result.download_speed_bps]
        tcp_latencies = [e.result.latency for e in valid if e.result.latency is not None]
        http_latencies = [e.result.http_latency for e in valid if e.result.http_latency is not None]
        top1 = valid[0]
        parts = [f"有效IP：{len(valid)}"]
        if speeds:
            parts.append(f"最快速度：{max(speeds) / 1048576:.2f} MB/s")
            parts.append(f"平均速度：{sum(speeds) / len(speeds) / 1048576:.2f} MB/s")
        if tcp_latencies:
            parts.append(f"最低延迟：{min(tcp_latencies)} ms")
            parts.append(f"平均TCP延迟：{sum(tcp_latencies) / len(tcp_latencies):.0f} ms")
        if http_latencies:
            parts.append(f"平均HTTP延迟：{sum(http_latencies) / len(http_latencies):.0f} ms")
        parts.append(f"TOP1：{top1.result.ip}（评分 {top1.score}）")
        self.result_summary_label.setText("　|　".join(parts))

    def _set_export_buttons_enabled(self, enabled: bool) -> None:
        """测速结束后才允许复制/导出（含节点相关按钮）。"""
        for button in (
            self.copy_top10_button, self.copy_top50_button, self.copy_top100_button,
            self.export_txt_button, self.export_csv_button,
            self.copy_selected_button, self.export_selected_button,
            self.copy_nodes_button, self.export_nodes_button,
        ):
            button.setEnabled(enabled)

    # ------------------------------------------------------------------
    # V1.4：稳定性复测的目标 / 启动 / 停止 / 进度
    # ------------------------------------------------------------------
    def _stability_targets(self) -> List[IPEntry]:
        """本次复测的目标 IP：当前 V1.3 排名里「可评分」的条目（已有 TOP N 截断）。

        失败 IP（rank=0 / score=None）不参与复测。
        """
        targets: List[IPEntry] = []
        for entry in self.result_table.rank_entries:
            if entry.score is None or entry.rank <= 0:
                continue
            targets.append(IPEntry(ip=entry.result.ip, port=entry.result.port))
        return targets

    def _on_stability_start(self) -> None:
        """开始稳定性复测（对当前 V1.3 排名的 TOP IP 做多轮重复测试）。"""
        if self._stability_running:
            return
        if self._running:
            QMessageBox.information(self, "提示", "测速正在进行，请等待结束或点击【停止测速】。")
            return
        if self._stability_worker is not None and self._stability_worker.isRunning():
            return
        targets = self._stability_targets()
        if not targets:
            QMessageBox.information(
                self, "提示",
                "当前没有可复测的 IP。\n\n请先完成一次测速，且排名中有评分有效的 IP。",
            )
            return

        rounds = self.stab_rounds_combo.currentData() or DEFAULT_STABILITY_ROUNDS
        concurrency = self.stab_concurrency_combo.currentData() or DEFAULT_STABILITY_CONCURRENCY
        self._stab_rounds_total = int(rounds)
        self._stab_ip_total = len(targets)

        # 复测参数与主测速保持一致（端口/超时/开关/下载大小全部来自界面）
        download_bytes = self.download_size_combo.currentData()
        if download_bytes is None:
            download_bytes = DEFAULT_DOWNLOAD_BYTES

        # 旧的复测汇总作废（表格仍保留 V1.3 排名显示，直到本轮复测完成）
        self._stability_map = {}
        self._stab_results_all = []
        self.export_stable_txt_button.setEnabled(False)
        self.export_stable_csv_button.setEnabled(False)

        self._stability_worker = StabilityWorker(
            targets,
            rounds=self._stab_rounds_total,
            concurrency=int(concurrency),
            port=self.port_spin.value(),
            timeout_ms=self.timeout_spin.value(),
            http_enabled=self.http_checkbox.isChecked(),
            http_timeout_ms=self.http_timeout_spin.value(),
            download_enabled=self.download_checkbox.isChecked(),
            download_bytes=int(download_bytes),
            download_timeout_ms=self.download_timeout_spin.value(),
            parent=self,
        )
        self._stability_worker.item_progress.connect(self._on_stability_item_progress)
        self._stability_worker.round_finished.connect(self._on_stability_round_finished)
        self._stability_worker.stability_finished.connect(self._on_stability_finished)
        self._stability_worker.stability_failed.connect(self._on_stability_failed)
        self._stability_worker.finished.connect(self._on_stability_worker_thread_finished)

        self._set_stability_running_state(True)
        self._stability_worker.start()
        logger.info(
            "用户点击【开始复测】，目标 %s 个 IP，%s 轮，并发 %s",
            self._stab_ip_total, self._stab_rounds_total, concurrency,
        )
        self._set_status("稳定性复测进行中……")

    def _on_stability_stop(self) -> None:
        """请求停止复测（已完成的轮次结果会保留并参与最终排名）。"""
        worker = self._stability_worker
        if worker is None or not worker.isRunning():
            return
        self.stab_start_button.setEnabled(False)
        self.stab_stop_button.setEnabled(False)
        self.stab_status_label.setText("正在停止复测，请稍候……")
        self._set_status("正在停止复测，请稍候……")
        logger.info("用户点击了停止复测")
        worker.request_stop()
        # V1.4：线程尚未完全结束就释放 `_stability_worker` 变量，不过 Qt 对象的
        # `finished` 信号还能触发（内部 worker 对象尚未析构），最终排名还是能算出，
        # 只是进度条等UI控件随后随线程生命周期一起销毁。这里算是“最保守”的处理方式。

    def _on_stability_item_progress(
        self, round_index: int, tested: int, total: int, current_ip: str
    ) -> None:
        """复测进度：按「已完成 IP 数 / 全部轮次总 IP 数」折算成总进度。"""
        rounds_total = max(1, self._stab_rounds_total)
        grand_total = max(1, rounds_total * max(1, self._stab_ip_total))
        done = (max(0, round_index - 1)) * max(1, self._stab_ip_total) + tested
        percent = int(min(100, max(0, done * 100 / grand_total)))
        self.stab_progress_bar.setValue(percent)
        self.stab_status_label.setText(
            f"复测中：第 {round_index}/{rounds_total} 轮，已测 {tested}/{total}"
        )
        if current_ip:
            self.stab_current_label.setText(f"当前：{current_ip}")

    def _on_stability_round_finished(self, round_index: int, results) -> None:
        """一轮复测结束：缓存该轮原始结果，供后续排查与复核。"""
        if results:
            self._stab_results_all.extend(list(results))
        self.stab_status_label.setText(
            f"第 {round_index} 轮完成（已缓存 {len(self._stab_results_all)} 条结果）"
        )

    def _on_stability_finished(self, stability_map, stopped: bool, elapsed: float) -> None:
        """全部复测结束：算最终排名并刷新表格/摘要/导出按钮。"""
        self._stability_map = dict(stability_map) if stability_map else {}
        entries = build_final_ranking(self.result_table.rank_entries, self._stability_map)
        has_final = bool(entries)
        if has_final:
            self.result_table.set_final_ranking(entries)
            self.result_table.enable_sorting()
        self.export_stable_txt_button.setEnabled(has_final)
        self.export_stable_csv_button.setEnabled(has_final)
        self._refresh_stability_summary(stopped, elapsed)
        self._refresh_stat_cards()
        self._set_stability_running_state(False)

        if not self._stability_map or not has_final:
            QMessageBox.information(
                self, "复测无有效结果",
                "复测完成了，但没有拿到可用的复测数据，结果表格保持 V1.3 排名不变。\n\n"
                "可能原因：网络中断、目标 IP 全部超时，或复测开始前就被停止。",
            )
            self._set_status("复测结束：无有效结果")
            return
        if stopped:
            QMessageBox.information(
                self, "已停止复测",
                f"复测已停止（用时 {elapsed:.1f} 秒），已用完成的轮次生成最终排名。\n\n"
                f"{self.stab_summary_label.text()}",
            )
            self._set_status("复测已停止（已按已完成轮次排名）")
        else:
            QMessageBox.information(
                self, "复测完成",
                f"稳定性复测完成，用时 {elapsed:.1f} 秒。\n\n"
                f"{self.stab_summary_label.text()}",
            )
            self._set_status("复测完成")
        logger.info(
            "复测完成：%s 个 IP 有复测数据，最终排名 %s 条，用时 %.1f 秒，用户停止=%s",
            len(self._stability_map), len(entries), elapsed, stopped,
        )

    def _on_stability_failed(self, message: str) -> None:
        """复测线程出错：恢复按钮，结果表格保持 V1.3 排名不变。"""
        self._set_stability_running_state(False)
        self.stab_status_label.setText("复测失败，请查看日志")
        logger.error("复测失败：%s", message)
        QMessageBox.critical(self, "复测失败", message)
        self._set_status("复测失败")

    def _on_stability_worker_thread_finished(self) -> None:
        """复测线程真正结束后释放对象（复测汇总已由 _on_stability_finished 保存）。"""
        worker = self._stability_worker
        self._stability_worker = None
        if worker is not None:
            worker.deleteLater()
        logger.info("复测线程对象已释放")

    def _has_stability_targets(self) -> bool:
        """是否存在可复测的 IP（V1.3 排名里至少有一个评分有效的 IP）。"""
        return any(
            entry.score is not None and entry.rank > 0
            for entry in self.result_table.rank_entries
        )

    def _refresh_stability_controls(self) -> None:
        """统一刷新复测按钮的可用状态。

        以下任意一种情况都会让「开始复测」不可用：
        - 主测速进行中（_running）；
        - 复测自己正在进行中（_stability_running）；
        - 没有可复测的 IP（还没测速，或筛选后全部失败）。
        「停止复测」只在复测进行中可用。
        """
        self.stab_start_button.setEnabled(
            not self._running and not self._stability_running and self._has_stability_targets()
        )
        self.stab_stop_button.setEnabled(self._stability_running)

    def _set_stability_running_state(self, running: bool) -> None:
        """切换复测进行中的控件可用状态（复测与主测速互斥）。

        复测进行中：V1.3 的筛选/复制/导出按钮暂时禁用，避免用户误以为
        还能用旧排名做导出；复测结束后由 _on_stability_finished 重新开启。
        """
        self._stability_running = running
        self.stab_rounds_combo.setEnabled(not running)
        self.stab_concurrency_combo.setEnabled(not running)
        # 复测/测速任一进行中，都不允许点主测速开始按钮，也不允许改导入/设置
        self.start_button.setEnabled(not running and not self._running)
        self.ip_panel.set_controls_enabled(not running and not self._running)
        # V1.3 的筛选/复制/导出按钮也与复测互斥（复测用的是同一批 TOP IP 集合）
        self.apply_filter_button.setEnabled(not running and not self._running)
        self._set_export_buttons_enabled(
            not running and not self._running and bool(self.result_table.rank_entries)
        )
        self._refresh_stability_controls()
        if running:
            # 新的一次复测：清空进度条与上一轮的摘要
            self.stab_progress_bar.setValue(0)
            self.stab_summary_label.setText("")
            self.stab_current_label.setText("当前：--")

    def _refresh_stability_summary(self, stopped: bool, elapsed: float) -> None:
        """刷新复测摘要：稳定/波动数量、平均稳定性、最高最终评分、TOP10。"""
        entries = self.result_table.final_entries
        if not entries:
            self.stab_summary_label.setText("复测完成：无有效结果")
            self.stab_status_label.setText("复测完成：无有效结果")
            return
        stable = [e for e in entries if e.stability_score >= STABLE_SCORE_THRESHOLD]
        unstable = len(entries) - len(stable)
        avg_stability = sum(e.stability_score for e in entries) / len(entries)
        best = max(entries, key=lambda e: e.final_score)
        top10 = "，".join(e.result.ip for e in entries[:10])
        self.stab_summary_label.setText(
            f"稳定IP：{len(stable)}　|　波动IP：{unstable}　|　"
            f"平均稳定性：{avg_stability:.0f}　|　"
            f"最高最终评分：{best.final_score}（{best.result.ip}）　|　"
            f"TOP10：{top10}"
        )
        self.stab_status_label.setText(
            f"复测{'已停止' if stopped else '完成'}：{len(entries)} 个 IP，用时 {elapsed:.1f} 秒"
        )

    def _on_export_stable_txt(self) -> None:
        """导出稳定 TOP TXT（按最终排名取前 100，每行一个 IP）。"""
        try:
            path = export_stable_txt(self.result_table.final_entries, top_n=DEFAULT_TOP_N)
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出成功", f"稳定 TOP TXT 已保存到：\n{path}")
        logger.info("用户导出稳定 TXT：%s", path)

    def _on_export_stable_csv(self) -> None:
        """导出稳定性 CSV（完整统计字段）。"""
        try:
            path = export_stable_csv(self.result_table.final_entries)
        except ExportError as exc:
            QMessageBox.warning(self, "导出失败", str(exc))
            return
        QMessageBox.information(self, "导出成功", f"稳定性 CSV 已保存到：\n{path}")
        logger.info("用户导出稳定性 CSV：%s", path)

    # ==================================================================
    # IP 导入
    # ==================================================================
    def _on_ips_imported(self, outcome) -> None:
        """IP 导入完成（由 IPPanel 通过信号通知）。"""
        self._valid_entries = self.ip_panel.valid_entries
        self._refresh_stat_cards()

        if outcome.summary.valid_count == 0:
            self._set_status("导入完成：没有可用的公网 IPv4 地址")
            return
        self._set_status(
            f"导入完成：{outcome.summary.valid_count} 个有效 IP，可以开始测速"
        )

    def _on_ips_cleared(self) -> None:
        """用户点击了【清空导入】。"""
        self._valid_entries = []
        self.result_summary_label.setText("")
        self._set_status("已清空导入内容")
        # V1.4：复测的原始汇总不再有效，但表格快照（V1.3 排名 / 最终排名）
        # 保持显示、导出仍可用，与此前 V1.3 “清空导入不清空结果”的行为一致。
        self._stability_map = {}
        self._stab_results_all = []
        has_final = bool(self.result_table.final_entries)
        self.export_stable_txt_button.setEnabled(has_final)
        self.export_stable_csv_button.setEnabled(has_final)
        if has_final:
            self.stab_status_label.setText("已清空导入（复测结果仍保留在表格中）")
        else:
            self.stab_status_label.setText("尚未复测")
            self.stab_summary_label.setText("")

    def _on_fetch_completed(self, summary_text: str) -> None:
        """自动获取 Cloudflare IP 完成（由 IPPanel 通知）。"""
        self._valid_entries = self.ip_panel.valid_entries
        self._refresh_stat_cards()
        self._set_status(f"{summary_text}，可以点击【开始测速】")

    def _on_fetch_failed(self, message: str) -> None:
        """自动获取 Cloudflare IP 失败。"""
        self._set_status(f"自动获取失败：{message}")

    # ==================================================================
    # 测速流程
    # ==================================================================
    def _on_start_scan(self) -> None:
        """开始测速。"""
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "提示", "测速正在进行，请等待结束或点击【停止测速】。")
            return
        if self._stability_running:
            QMessageBox.information(self, "提示", "稳定性复测正在进行，请等待结束或点击【停止复测】。")
            return
        if not self._valid_entries:
            QMessageBox.warning(self, "提示", "还没有可用的 IP，请先导入 IP。")
            return

        port = self.port_spin.value()
        concurrency = self.concurrency_spin.value()
        timeout_ms = self.timeout_spin.value()

        # ---- V1.2：第二级 HTTP 与第三级 下载 的参数（全部来自界面，可随时调整）----
        http_enabled = self.http_checkbox.isChecked()
        http_timeout_ms = self.http_timeout_spin.value()
        download_enabled = self.download_checkbox.isChecked()
        download_bytes = self.download_size_combo.currentData()
        if download_bytes is None:  # 极端情况下取不到数据，退回默认值
            download_bytes = DEFAULT_DOWNLOAD_BYTES
        download_timeout_ms = self.download_timeout_spin.value()

        total = len(self._valid_entries)

        # 重置界面与缓存
        self._pending_results.clear()
        self._all_results.clear()
        self.result_table.clear_results()
        # V1.4：新一轮测速会使旧的复测结果失效，先清空复测状态
        self._stability_map = {}
        self._stab_results_all = []
        self.export_stable_txt_button.setEnabled(False)
        self.export_stable_csv_button.setEnabled(False)
        self.stab_status_label.setText("尚未复测")
        self.stab_summary_label.setText("")
        self.stab_current_label.setText("当前：--")
        self.stab_progress_bar.setValue(0)
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.tested_label.setText(f"已测试：0 / {total}")
        self.success_label.setText("成功：0")
        self.failed_label.setText("失败：0")
        self.elapsed_label.setText("用时：0.0 秒")
        self._reset_stage_labels(total)
        self.result_summary_label.setText("测速进行中……")

        # 创建后台测速线程
        self._worker = ScanWorker(
            self._valid_entries,
            port,
            concurrency,
            timeout_ms,
            http_enabled=http_enabled,
            http_timeout_ms=http_timeout_ms,
            download_enabled=download_enabled,
            download_bytes=int(download_bytes),
            download_timeout_ms=download_timeout_ms,
            parent=self,
        )
        self._worker.result_ready.connect(self._on_result_ready)
        self._worker.progress_changed.connect(self._on_progress_changed)
        self._worker.stage_changed.connect(self._on_stage_changed)  # V1.2：各阶段统计
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.scan_failed.connect(self._on_scan_failed)
        self._worker.finished.connect(self._on_worker_thread_finished)

        self._scan_start_time = time.perf_counter()
        self._set_running_state(True)
        self._flush_timer.start()
        self._elapsed_timer.start()
        # 注意：_set_running_state(True) 已经把「开始复测」按钮一并禁用，
        # 所以复测与主测速不会同时运行，无需额外的抢占标记。
        self._worker.start()

        # 具体的测速参数由 core/scanner.py 记录日志，这里只提示用户操作
        logger.info(
            "用户点击【开始测速】，目标 %s 个（HTTP测试=%s，下载测速=%s）",
            total,
            "开启" if http_enabled else "关闭",
            "开启" if download_enabled else "关闭",
        )
        self._set_status("测速进行中……")

    def _on_stop_scan(self) -> None:
        """请求停止测速。"""
        if self._worker is None or not self._worker.isRunning():
            return

        # 停止过程中按钮保持禁用，等线程安全退出后再恢复
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(False)
        self.result_summary_label.setText("正在停止测速，请稍候……")
        self._set_status("正在停止测速，请稍候……")
        logger.info("用户点击了停止测速")
        self._worker.request_stop()

    def _on_result_ready(self, result: TestResult) -> None:
        """收到一个测速结果（先缓存，稍后批量写入表格）。

        结果先进 _pending_results 缓存，由 _flush_results 定时批量写表格；
        同时存进 _all_results，测速结束后用于计算综合评分与排名。
        """
        self._pending_results.append(result)
        self._all_results.append(result)

    def _flush_results(self) -> None:
        """把缓存的结果批量写入表格。"""
        if not self._pending_results:
            return
        batch = self._pending_results
        self._pending_results = []
        self.result_table.add_results(batch)

    def _on_progress_changed(self, tested: int, success: int, failed: int, total: int) -> None:
        """刷新进度显示。"""
        self.progress_bar.setValue(min(tested, total))
        self.tested_label.setText(f"已测试：{tested} / {total}")
        self.success_label.setText(f"成功：{success}")
        self.failed_label.setText(f"失败：{failed}")

    # ------------------------------------------------------------------
    # V1.2：三级测试（TCP / HTTP / 下载）各自的成功 / 失败统计
    # ------------------------------------------------------------------
    def _reset_stage_labels(self, total: int) -> None:
        """开始测速前，把各阶段统计清零（初始时全部阶段都还没测试）。"""
        self.tcp_stat_label.setText("TCP 成功 0 / 失败 0")
        self.http_stat_label.setText(f"HTTP 成功 0 / 失败 0 / 未测试 {total}")
        self.download_stat_label.setText(f"下载 成功 0 / 失败 0 / 未测试 {total}")

    def _on_stage_changed(self, stats: StageStats) -> None:
        """收到各阶段统计快照，刷新标签。

        「未测试」表示这个阶段没有被执行：
        - HTTP 未测试 = TCP 没通的 IP + 用户关闭了 HTTP 测试
        - 下载未测试 = TCP 或 HTTP 没通的 IP + 用户关闭了下载测速
        """
        self.tcp_stat_label.setText(f"TCP 成功 {stats.tcp_success} / 失败 {stats.tcp_failed}")

        http_untested = max(0, stats.tcp_tested - stats.http_tested)
        self.http_stat_label.setText(
            f"HTTP 成功 {stats.http_success} / 失败 {stats.http_failed} / 未测试 {http_untested}"
        )

        download_untested = max(0, stats.tcp_tested - stats.download_tested)
        self.download_stat_label.setText(
            f"下载 成功 {stats.download_success} / 失败 {stats.download_failed} / "
            f"未测试 {download_untested}"
        )

    def _refresh_elapsed(self) -> None:
        """定时刷新“用时”（测速进行中，即使没有新结果也会走动）。"""
        self.elapsed_label.setText(f"用时：{self._elapsed_seconds():.1f} 秒")

    def _on_scan_finished(self, summary: ScanSummary, elapsed: float) -> None:
        """测速结束：排序显示结果并恢复按钮状态。"""
        self._flush_timer.stop()
        self._elapsed_timer.stop()
        self._flush_results()

        # V1.3：按综合评分排名显示（含筛选与 TOP N），并生成结果摘要
        self._refresh_ranking_view()
        self._set_export_buttons_enabled(True)

        self.progress_bar.setValue(min(summary.tested, summary.total))
        self.tested_label.setText(f"已测试：{summary.tested} / {summary.total}")
        self.success_label.setText(f"成功：{summary.success}")
        self.failed_label.setText(f"失败：{summary.failed}")
        self.elapsed_label.setText(f"用时：{elapsed:.1f} 秒")
        # 用最终汇总信息刷新各阶段统计，保证显示的数字与汇总完全一致
        self._on_stage_changed(StageStats.from_summary(summary))

        self._set_running_state(False)
        logger.info(
            "测速完成：完成 %s/%s，TCP 成功 %s / 失败 %s，HTTP 成功 %s / 失败 %s，"
            "下载成功 %s / 失败 %s，用时 %.1f 秒，用户停止=%s",
            summary.tested,
            summary.total,
            summary.success,
            summary.failed,
            summary.http_success,
            summary.http_failed,
            summary.download_success,
            summary.download_failed,
            elapsed,
            summary.stopped,
        )

        if summary.stopped:
            QMessageBox.information(
                self,
                "已停止测速",
                f"测速已停止，已保留 {summary.tested} 条结果。\n\n"
                f"TCP 成功：{summary.success}，失败：{summary.failed}\n"
                f"HTTP 成功：{summary.http_success}，失败：{summary.http_failed}\n"
                f"下载成功：{summary.download_success}，失败：{summary.download_failed}",
            )
            self._set_status("测速已停止")
        else:
            QMessageBox.information(
                self,
                "测速完成",
                f"测速完成，用时 {elapsed:.1f} 秒。\n\n"
                f"共测试：{summary.tested}\n\n"
                f"TCP 成功：{summary.success}，失败：{summary.failed}\n"
                f"HTTP 成功：{summary.http_success}，失败：{summary.http_failed}\n"
                f"下载成功：{summary.download_success}，失败：{summary.download_failed}",
            )
            self._set_status("测速完成")

    def _on_scan_failed(self, message: str) -> None:
        """测速线程出错。"""
        self._flush_timer.stop()
        self._elapsed_timer.stop()
        self._flush_results()
        self._set_running_state(False)
        self.result_summary_label.setText("测速失败，请查看日志")
        logger.error("测速失败：%s", message)
        QMessageBox.critical(self, "测速失败", message)
        self._set_status("测速失败")

    def _on_worker_thread_finished(self) -> None:
        """线程真正结束后释放对象。"""
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()

    def _set_running_state(self, running: bool) -> None:
        """根据是否正在测速，切换控件的可用状态。"""
        self._running = running
        self.start_button.setEnabled(not running and not self._stability_running)
        self.stop_button.setEnabled(running)
        self.ip_panel.set_controls_enabled(not running and not self._stability_running)
        self.port_spin.setEnabled(not running)
        self.concurrency_spin.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        # V1.2：第二级 / 第三级的控件也要一起锁定/解锁
        # （_on_http_toggled 与 _on_download_toggled 会根据 _running 和开关状态算出正确结果）
        self.http_checkbox.setEnabled(not running)
        self._on_http_toggled(self.http_checkbox.isChecked())
        # V1.3：测速期间禁用复制/导出（结束后由 _on_scan_finished 重新开启）
        self._set_export_buttons_enabled(not running and bool(self.result_table.rank_entries))
        # V1.4：测速期间禁用复测开始按钮（结束后有可复测的 IP 才可用）
        self._refresh_stability_controls()

    def _elapsed_seconds(self) -> float:
        """本轮测速已运行的时间（秒）。"""
        if not self._scan_start_time:
            return 0.0
        return time.perf_counter() - self._scan_start_time

    # ==================================================================
    # 关闭窗口
    # ==================================================================
    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt 规定的命名)
        """关闭窗口时，如果正在测速，先安全停止线程。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            answer = QMessageBox.question(
                self,
                "确认退出",
                "测速正在进行，确定要退出吗？\n（会停止测速，并保留已经得到的结果）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

            logger.info("关闭窗口：正在停止测速线程")
            self._flush_timer.stop()
            self._elapsed_timer.stop()
            worker.request_stop()
            # V1.4：复测线程同样请求停止（已完成轮次的结果已保留在内存中）
            stab_worker = self._stability_worker
            if stab_worker is not None and stab_worker.isRunning():
                logger.info("关闭窗口：正在停止复测线程")
                stab_worker.request_stop()

            # 先等一小会儿；如果线程还没结束（例如超时设置很大），
            # 就先隐藏窗口，等线程安全结束后再自动退出，避免强杀线程导致崩溃。
            if not worker.wait(3000):
                logger.info("测速线程仍在收尾，窗口先隐藏，结束后自动退出")
                self.hide()
                self._set_status("正在停止测速，程序即将自动退出……")
                self._start_quit_timer()
                event.ignore()
                return

        # V1.4：如果只有复测线程在跑，同样先安全停止再退出（先向用户确认一次）
        stab_worker = self._stability_worker
        if stab_worker is not None and stab_worker.isRunning():
            answer = QMessageBox.question(
                self,
                "确认退出",
                "稳定性复测正在进行，确定要退出吗？\n（会停止复测，已完成的轮次不会被保存）",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            logger.info("关闭窗口：正在停止复测线程")
            stab_worker.request_stop()
            if not stab_worker.wait(3000):
                logger.info("复测线程仍在收尾，窗口先隐藏，结束后自动退出")
                self.hide()
                self._set_status("正在停止复测，程序即将自动退出……")
                self._start_quit_timer()
                event.ignore()
                return

        # 自动获取线程只是单个 HTTP 请求，最多等 3 秒即可安全退出
        self.ip_panel.shutdown_fetch()

        # 抽样测速线程同样要安全收尾（会保存当前结果与配置）
        if hasattr(self, "sample_page"):
            self.sample_page.shutdown()

        logger.info("程序关闭：主窗口已关闭")
        event.accept()

    def _start_quit_timer(self) -> None:
        """启动定时器，定期检查测速线程是否已经结束。"""
        if self._quit_timer is not None:
            return
        self._quit_timer = QTimer(self)
        self._quit_timer.setInterval(200)
        self._quit_timer.timeout.connect(self._check_worker_before_quit)
        self._quit_timer.start()

    def _check_worker_before_quit(self) -> None:
        """测速线程结束后，真正关闭程序。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            return
        # V1.4：复测线程也必须结束才能退出
        stab_worker = self._stability_worker
        if stab_worker is not None and stab_worker.isRunning():
            return

        if self._quit_timer is not None:
            self._quit_timer.stop()
            self._quit_timer = None
        self.close()  # 再次触发 closeEvent，此时线程已经结束