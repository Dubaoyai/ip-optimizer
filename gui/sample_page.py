"""抽样测速页面（第四视图）。

移植自《优选IP测速_重构版.html》，功能一一对应：

    原 HTML 控件                     本页面控件
    -----------------------------  ------------------------------------
    CIDR 网段列表（可编辑+持久化）    self.cidr_edit / _save_prefs
    代理模板（可编辑）                self.template_edit
    测速源下拉                        self.source_combo
    探测端口多选                      self.port_selector
    每段抽样 / 并发 / 超时 / 保留N     self.per_cidr / concurrency / timeout / keep_n
    抽样测速（单次）                  self.start_button
    自动抽样                          self.auto_button
    停止                              self.stop_button
    清空结果                          self.clear_button
    一键复制最优N条                   self.copy_best_button
    复制全部可用                      self.copy_pass_button
    复制 IP 列表                      self.copy_ip_button
    下载全部可用                      self.download_button
    结果表格（#/IP/端口/延迟/代理节点） self.table
    统计（候选/已测/可用·保留/最优）   self.stat_cards
    汇总（存活率/平均延迟/端口分布）   self.rate_label / avg_label / port_label

与原版的差异（有意为之）：
- 测速引擎改用 Python 真实 TCP+HTTP 探测（浏览器受 CORS 限制只能 no-cors）；
- 结果持久化改用本地 json 文件（原版用 localStorage）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.sampler import (
    BUILT_IN_PORTS,
    DEFAULT_CIDRS,
    DEFAULT_CONCURRENCY,
    DEFAULT_KEEP_N,
    DEFAULT_PORTS,
    DEFAULT_SAMPLE_PER_CIDR,
    DEFAULT_TEMPLATE,
    DEFAULT_TIMEOUT_MS,
    FAST_MS,
    MID_MS,
    SOURCE_LABELS,
    SPEED_SOURCES,
    ProbeResult,
    SampleEngine,
    SampleStats,
    extract_template_port,
    resolve_probe_ports,
    summarize,
)
from gui import theme, widgets
from gui.sample_worker import SampleWorker
from utils.logger import get_logger
from utils.paths import data_root

logger: logging.Logger = get_logger()

# 偏好文件（与主题偏好同目录；原版用 localStorage）
PREFS_FILE = "sample_prefs.json"
RESULTS_FILE = "sample_results.json"

# 结果表列
HEADERS = ("#", "IP", "端口", "延迟", "代理节点")


class SamplePage(QWidget):
    """抽样测速页面：CIDR 抽样 → 并发测速 → 生成可用节点。"""

    def __init__(self, parent=None) -> None:
        """初始化页面。"""
        super().__init__(parent)
        self.setObjectName("PageContainer")

        self._engine = SampleEngine()
        self._worker: Optional[SampleWorker] = None
        self._running = False

        self._build_ui()
        self._load_prefs()
        self._load_results()
        self._refresh_buttons()
        logger.info("抽样测速页面初始化完成")

    # ==================================================================
    # 界面
    # ==================================================================
    def _build_ui(self) -> None:
        """搭建界面：左侧配置 + 右侧结果（对应原 HTML 的两栏布局）。"""
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(theme.GAP_CARD)

        root.addWidget(self._build_config_panel(), 0)
        root.addWidget(self._build_result_panel(), 1)

    # ------------------------------------------------------------------
    # 左栏：配置
    # ------------------------------------------------------------------
    def _build_config_panel(self) -> QWidget:
        """构建左侧配置面板。"""
        panel = widgets.Panel("配置", "CIDR 网段 · 代理模板 · 测速参数")
        panel.setFixedWidth(360)
        body = panel.body_layout

        # ---- CIDR 网段 ----
        cidr_head = QHBoxLayout()
        cidr_head.setSpacing(6)
        cidr_head.addWidget(widgets.hint_label("CIDR 网段列表", "secondary"))
        cidr_head.addStretch(1)
        self.cidr_count_label = widgets.hint_label("0 段", "muted")
        cidr_head.addWidget(self.cidr_count_label)
        body.addLayout(cidr_head)

        self.cidr_edit = QPlainTextEdit()
        self.cidr_edit.setPlaceholderText("每行一个 CIDR，例如：\n104.16.0.0/13\n172.64.0.0/13")
        self.cidr_edit.setFixedHeight(150)
        self.cidr_edit.textChanged.connect(self._on_cidr_changed)
        body.addWidget(self.cidr_edit)

        # ---- 代理模板 ----
        body.addWidget(widgets.hint_label("代理模板（可手动修改）", "secondary"))
        self.template_edit = QPlainTextEdit()
        self.template_edit.setPlaceholderText("vless://uuid@1.2.3.4:443?encryption=none&security=none&type=ws")
        self.template_edit.setFixedHeight(84)
        self.template_edit.textChanged.connect(self._on_template_changed)
        body.addWidget(self.template_edit)
        self.template_hint = widgets.hint_label("模板需包含 @IP:端口 片段，测速后自动替换", "muted")
        body.addWidget(self.template_hint)

        # ---- 测速源 ----
        body.addWidget(widgets.hint_label("测速源", "secondary"))
        self.source_combo = QComboBox()
        for key, label in SOURCE_LABELS.items():
            self.source_combo.addItem(label, key)
        body.addWidget(self.source_combo)

        # ---- 探测端口（多选）----
        body.addWidget(widgets.hint_label("探测端口（勾选生效）", "secondary"))
        self.port_selector = widgets.PortSelector(BUILT_IN_PORTS, DEFAULT_PORTS)
        self.port_selector.changed.connect(self._save_prefs)
        body.addWidget(self.port_selector)

        # ---- 四个数值参数（2×2 栅格，与原版布局一致）----
        grid = QGridLayout()
        grid.setSpacing(8)

        grid.addWidget(widgets.hint_label("每段抽样", "muted"), 0, 0)
        self.per_cidr_spin = QSpinBox()
        self.per_cidr_spin.setRange(10, 5000)
        self.per_cidr_spin.setValue(DEFAULT_SAMPLE_PER_CIDR)
        self.per_cidr_spin.setToolTip("每个 CIDR 网段随机抽取多少个 IP 参与测速")
        grid.addWidget(self.per_cidr_spin, 1, 0)

        grid.addWidget(widgets.hint_label("并发数", "muted"), 0, 1)
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 500)
        self.concurrency_spin.setValue(DEFAULT_CONCURRENCY)
        self.concurrency_spin.setToolTip("同时探测多少个 IP（越大越快，对网络压力也越大）")
        grid.addWidget(self.concurrency_spin, 1, 1)

        grid.addWidget(widgets.hint_label("超时(ms)", "muted"), 2, 0)
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(100, 10000)
        self.timeout_spin.setValue(DEFAULT_TIMEOUT_MS)
        self.timeout_spin.setSingleStep(100)
        grid.addWidget(self.timeout_spin, 3, 0)

        grid.addWidget(widgets.hint_label("保留最优N", "muted"), 2, 1)
        self.keep_n_spin = QSpinBox()
        self.keep_n_spin.setRange(1, 1000)
        self.keep_n_spin.setValue(DEFAULT_KEEP_N)
        self.keep_n_spin.setToolTip("「一键复制最优N条」复制多少条")
        grid.addWidget(self.keep_n_spin, 3, 1)

        body.addLayout(grid)

        # 数值参数变化时同样保存（此前只有 CIDR/模板/端口 有保存，参数改了不落盘）
        self.per_cidr_spin.valueChanged.connect(self._save_prefs)
        self.concurrency_spin.valueChanged.connect(self._save_prefs)
        self.timeout_spin.valueChanged.connect(self._save_prefs)
        self.keep_n_spin.valueChanged.connect(self._save_prefs)
        self.source_combo.currentIndexChanged.connect(self._save_prefs)

        # ---- 操作按钮 ----
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.start_button = widgets.primary_button("抽样测速", "按当前配置抽一轮并测速")
        self.start_button.clicked.connect(self._on_start)
        self.auto_button = widgets.ghost_button(
            "自动抽样", "连续抽取直到覆盖完当前可抽 IP 库（或点停止）"
        )
        self.auto_button.clicked.connect(self._on_auto)
        self.stop_button = widgets.danger_button("停止", "停止抽样测速（已完成的结果保留）")
        self.stop_button.clicked.connect(self._on_stop)
        self.stop_button.setEnabled(False)
        for b in (self.start_button, self.auto_button, self.stop_button):
            btn_row.addWidget(b)
        body.addLayout(btn_row)

        # ---- 进度 ----
        body.addWidget(widgets.hint_label("测速进度", "secondary"))
        self.progress_bar = widgets.ProgressBar()
        body.addWidget(self.progress_bar)

        self.status_label = widgets.hint_label("抽样模块就绪", "muted")
        body.addWidget(self.status_label)

        body.addStretch(1)
        return panel

    # ------------------------------------------------------------------
    # 右栏：结果
    # ------------------------------------------------------------------
    def _build_result_panel(self) -> QWidget:
        """构建右侧结果面板。"""
        panel = widgets.Panel("优选排名", "抽样测速")
        body = panel.body_layout

        # ---- 四个统计卡 ----
        self.stat_cards: Dict[str, widgets.StatCard] = {}
        card_row = QHBoxLayout()
        card_row.setSpacing(10)
        for key, label, unit, icon, color_key in (
            ("cand", "候选", "", "▦", "ACCENT"),
            ("test", "已测", "", "✓", "BLUE"),
            ("pass", "可用", "", "≡", "GREEN"),
            ("fast", "最优", "ms", "◷", "ORANGE"),
        ):
            card = widgets.StatCard(label, "0", unit, icon, color_key)
            self.stat_cards[key] = card
            card_row.addWidget(card, 1)
        body.addLayout(card_row)

        # ---- 汇总行 ----
        summary_row = QHBoxLayout()
        summary_row.setSpacing(16)
        self.rate_label = widgets.hint_label("存活率: --", "muted")
        self.avg_label = widgets.hint_label("平均延迟: --", "muted")
        self.port_label = widgets.hint_label("端口分布: --", "muted")
        for lb in (self.rate_label, self.avg_label, self.port_label):
            summary_row.addWidget(lb)
        summary_row.addStretch(1)
        body.addLayout(summary_row)

        # ---- 操作按钮行 ----
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.copy_best_button = widgets.primary_button(
            "一键复制最优N条", "复制前 N 条节点链接，可直接在 V2RayN 从剪贴板导入"
        )
        self.copy_best_button.clicked.connect(self._on_copy_best)
        self.copy_pass_button = widgets.ghost_button("复制全部可用", "复制全部可用节点链接")
        self.copy_pass_button.clicked.connect(self._on_copy_pass)
        self.copy_ip_button = widgets.ghost_button("复制IP列表", "只复制 IP，每行一个")
        self.copy_ip_button.clicked.connect(self._on_copy_ip)
        self.download_button = widgets.ghost_button("下载全部可用", "把全部可用节点保存为 txt")
        self.download_button.clicked.connect(self._on_download)
        self.clear_button = widgets.danger_button("清空结果", "清空结果与已测记录，可重新抽样")
        self.clear_button.clicked.connect(self._on_clear)
        for b in (
            self.copy_best_button, self.copy_pass_button,
            self.copy_ip_button, self.download_button, self.clear_button,
        ):
            action_row.addWidget(b)
        action_row.addStretch(1)
        body.addLayout(action_row)

        # ---- 结果表格 ----
        self.table = QTableWidget(0, len(HEADERS))
        self.table.setHorizontalHeaderLabels(list(HEADERS))
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(28)
        self.table.horizontalHeader().setFixedHeight(34)
        self.table.setShowGrid(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        body.addWidget(self.table, 1)

        # 空态提示
        self.empty_label = widgets.hint_label("暂无结果 —— 点击左侧【抽样测速】开始", "muted")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.addWidget(self.empty_label)

        return panel

    # ==================================================================
    # 偏好与结果持久化（对应原版 localStorage）
    # ==================================================================
    def _prefs_path(self) -> Path:
        """偏好文件路径。"""
        return data_root() / PREFS_FILE

    def _results_path(self) -> Path:
        """结果文件路径。"""
        return data_root() / RESULTS_FILE

    def _load_prefs(self) -> None:
        """读取上次的配置（不存在时用默认值）。

        注意：恢复过程中**屏蔽所有保存触发**，避免"读到一半就把半截配置写回盘"
        （曾导致后读的项覆盖先读的项）；全部恢复完毕后不主动保存。
        """
        # 先填默认值
        self.cidr_edit.blockSignals(True)
        self.template_edit.blockSignals(True)
        self.cidr_edit.setPlainText(DEFAULT_CIDRS)
        self.template_edit.setPlainText(DEFAULT_TEMPLATE)
        self.cidr_edit.blockSignals(False)
        self.template_edit.blockSignals(False)

        path = self._prefs_path()
        if not path.exists():
            self._on_cidr_changed()
            self._on_template_changed()
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("抽样配置读取失败，使用默认值")
            self._on_cidr_changed()
            self._on_template_changed()
            return

        # 恢复期间屏蔽一切信号，恢复完再统一刷新提示
        widgets_to_block = (
            self.cidr_edit, self.template_edit, self.source_combo,
            self.per_cidr_spin, self.concurrency_spin,
            self.timeout_spin, self.keep_n_spin,
        )
        for w in widgets_to_block:
            w.blockSignals(True)
        try:
            if isinstance(data.get("cidr"), str) and data["cidr"].strip():
                self.cidr_edit.setPlainText(data["cidr"])
            if isinstance(data.get("template"), str) and data["template"].strip():
                self.template_edit.setPlainText(data["template"])
            for key, spin in (
                ("per_cidr", self.per_cidr_spin),
                ("concurrency", self.concurrency_spin),
                ("timeout", self.timeout_spin),
                ("keep_n", self.keep_n_spin),
            ):
                value = data.get(key)
                if isinstance(value, int):
                    spin.setValue(value)
            if isinstance(data.get("source"), str):
                idx = self.source_combo.findData(data["source"])
                if idx >= 0:
                    self.source_combo.setCurrentIndex(idx)
        finally:
            for w in widgets_to_block:
                w.blockSignals(False)

        ports = data.get("ports")
        if isinstance(ports, list) and ports:
            self.port_selector.set_selected([int(p) for p in ports if str(p).isdigit()])

        # 统一刷新一次派生显示（段数、模板提示）
        self._on_cidr_changed()
        self._on_template_changed()

    def _save_prefs(self) -> None:
        """保存当前配置（失败不影响使用）。"""
        try:
            data = {
                "cidr": self.cidr_edit.toPlainText(),
                "template": self.template_edit.toPlainText(),
                "per_cidr": self.per_cidr_spin.value(),
                "concurrency": self.concurrency_spin.value(),
                "timeout": self.timeout_spin.value(),
                "keep_n": self.keep_n_spin.value(),
                "source": self.source_combo.currentData(),
                "ports": self.port_selector.selected_ports(),
            }
            path = self._prefs_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            logger.exception("保存抽样配置失败")

    def _load_results(self) -> None:
        """读取上次的测速结果（对应 loadResults）。"""
        path = self._results_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            passing = data.get("passing") or []
            tested = data.get("tested") or []
        except Exception:
            logger.warning("抽样结果读取失败，忽略")
            return

        for item in passing:
            try:
                self._engine.passing.append(
                    ProbeResult(
                        ip=item["ip"], port=int(item["port"]),
                        ms=float(item["ms"]), node=item["node"],
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue
        self._engine.tested = set(str(x) for x in tested)
        self._engine.passing.sort(key=lambda r: r.ms)
        if self._engine.passing:
            self._render_table()
            self._update_stats()

    def _save_results(self) -> None:
        """保存测速结果（对应 saveResults）。"""
        try:
            data = {
                "passing": [
                    {"ip": r.ip, "port": r.port, "ms": r.ms, "node": r.node}
                    for r in self._engine.passing
                ],
                "tested": sorted(self._engine.tested),
            }
            path = self._results_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.exception("保存抽样结果失败")

    # ==================================================================
    # 事件：输入变化
    # ==================================================================
    def _on_cidr_changed(self) -> None:
        """CIDR 文本变化：更新段数并保存。"""
        count = len([
            line for line in self.cidr_edit.toPlainText().splitlines()
            if line.split("#")[0].strip()
        ])
        self.cidr_count_label.setText(f"{count} 段")
        self._save_prefs()

    def _on_template_changed(self) -> None:
        """模板变化：校验是否含 @IP:端口，并保存。"""
        parsed = extract_template_port(self.template_edit.toPlainText())
        if parsed:
            self.template_hint.setText(f"已识别端点：@{'{ip}'}:{parsed[0]}（测速后自动替换）")
            self.template_hint.setObjectName("Success")
        else:
            self.template_hint.setText("⚠ 模板中未找到 @IP:端口 格式，无法生成节点")
            self.template_hint.setObjectName("Warning")
        # objectName 变了要重新应用样式
        self.template_hint.style().unpolish(self.template_hint)
        self.template_hint.style().polish(self.template_hint)
        self._save_prefs()

    # ==================================================================
    # 测速流程
    # ==================================================================
    def _build_worker(self, auto: bool) -> Optional[SampleWorker]:
        """按当前界面配置构造测速线程。

        Args:
            auto: 是否自动连抽模式。

        Returns:
            SampleWorker；配置有问题时返回 None（并已提示用户）。
        """
        template = self.template_edit.toPlainText()
        parsed = extract_template_port(template)
        if parsed is None:
            QMessageBox.warning(
                self, "模板格式有误",
                "代理模板中未找到 @IP:端口 格式。\n\n"
                "示例：vless://uuid@1.2.3.4:443?encryption=none\n"
                "其中的 @1.2.3.4:443 会被替换为实测通过的 IP 与端口。",
            )
            return None

        cidr_text = self.cidr_edit.toPlainText()
        if not any(line.split("#")[0].strip() for line in cidr_text.splitlines()):
            QMessageBox.warning(self, "缺少网段", "请先在左侧填写至少一个 CIDR 网段。")
            return None

        ports = resolve_probe_ports(self.port_selector.selected_ports(), parsed[0])
        return SampleWorker(
            engine=self._engine,
            cidr_text=cidr_text,
            per_cidr=self.per_cidr_spin.value(),
            ports=ports,
            template=template,
            source=self.source_combo.currentData(),
            timeout_ms=self.timeout_spin.value(),
            concurrency=self.concurrency_spin.value(),
            auto=auto,
            parent=self,
        )

    def _on_start(self) -> None:
        """抽样测速（单次）。"""
        if self._running:
            return
        worker = self._build_worker(auto=False)
        if worker is None:
            return
        self._begin_run(worker, "抽样测速（单次）运行中……（结果累积，不自动清理）")

    def _on_auto(self) -> None:
        """自动抽样（连续抽取直到覆盖完或停止）。"""
        if self._running:
            return
        worker = self._build_worker(auto=True)
        if worker is None:
            return
        self._begin_run(worker, "自动抽样运行中……（连续抽取，点【停止】结束）")

    def _begin_run(self, worker: SampleWorker, status_text: str) -> None:
        """启动线程并接线信号。"""
        self._running = True
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.passage_found.connect(self._on_pass)
        worker.round_finished.connect(self._on_round_finished)
        worker.finished_all.connect(self._on_finished)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_thread_finished)

        self._set_running_state(True)
        self.status_label.setText(status_text)
        self.empty_label.setVisible(False)
        worker.start()
        logger.info("抽样测速启动（自动=%s）", worker._auto)

    def _on_stop(self) -> None:
        """停止测速。"""
        if self._worker is not None and self._worker.isRunning():
            self._worker.request_stop()
            self.stop_button.setEnabled(False)
            self.status_label.setText("正在停止，请稍候……")
            logger.info("用户点击了停止抽样")

    def _on_progress(self, done: int, total: int) -> None:
        """进度更新。"""
        self.progress_bar.setValue(done, total)
        self.stat_cards["test"].set_value(str(done), "BLUE")

    def _on_pass(self, result: ProbeResult) -> None:
        """发现可用节点：追加到表格并更新统计。"""
        self._render_table()
        self._update_stats()

    def _on_round_finished(self, fresh: int) -> None:
        """一轮结束。"""
        self._save_results()
        self._update_stats()

    def _on_finished(self, stats: SampleStats) -> None:
        """全部结束。"""
        self._update_stats()
        self._save_results()
        self._set_running_state(False)
        if stats.passing:
            self.status_label.setObjectName("Success")
            self.status_label.setText(
                f"抽样结束：累计可用 {stats.passing} 个，最优 {stats.fastest_ms:.0f} ms"
                if stats.fastest_ms is not None
                else f"抽样结束：累计可用 {stats.passing} 个"
            )
        else:
            self.status_label.setObjectName("Muted")
            self.status_label.setText("抽样结束：本轮未发现可用节点，可调整端口/超时后重试")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_failed(self, message: str) -> None:
        """出错。"""
        self._set_running_state(False)
        self.status_label.setText(f"抽样失败：{message}")
        QMessageBox.critical(self, "抽样测速失败", message)

    def _on_thread_finished(self) -> None:
        """线程结束：释放对象。"""
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._set_running_state(False)

    def _set_running_state(self, running: bool) -> None:
        """切换运行态的控件可用性。"""
        self._running = running
        self.start_button.setEnabled(not running)
        self.auto_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.clear_button.setEnabled(not running)
        self.cidr_edit.setEnabled(not running)
        self.template_edit.setEnabled(not running)
        self.source_combo.setEnabled(not running)
        self.per_cidr_spin.setEnabled(not running)
        self.concurrency_spin.setEnabled(not running)
        self.timeout_spin.setEnabled(not running)
        self.keep_n_spin.setEnabled(not running)
        self.port_selector.set_enabled_ui(not running)
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        """按是否有结果刷新复制/下载/清空按钮。"""
        has = bool(self._engine.passing)
        for b in (
            self.copy_best_button, self.copy_pass_button,
            self.copy_ip_button, self.download_button,
        ):
            b.setEnabled(has and not self._running)
        self.clear_button.setEnabled(not self._running)

    # ==================================================================
    # 结果渲染与统计
    # ==================================================================
    def _render_table(self) -> None:
        """重绘结果表格（对应 renderTable）。"""
        records = self._engine.passing
        self.empty_label.setVisible(not records)
        self.table.setRowCount(len(records))

        for row, rec in enumerate(records):
            idx_item = QTableWidgetItem(str(row + 1))
            idx_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            idx_item.setForeground(theme.COLOR_MUTED)
            self.table.setItem(row, 0, idx_item)

            ip_item = QTableWidgetItem(rec.ip)
            ip_item.setForeground(theme.COLOR_PRIMARY)
            self.table.setItem(row, 1, ip_item)

            port_item = QTableWidgetItem(str(rec.port))
            port_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            port_item.setForeground(theme.COLOR_MUTED)
            self.table.setItem(row, 2, port_item)

            ms_item = QTableWidgetItem(f"{rec.ms:.0f} ms")
            ms_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            # 延迟配色：<100 绿 / <300 橙 / 其余红（与原版行样式一致）
            if rec.ms < FAST_MS:
                ms_item.setForeground(theme.COLOR_SUCCESS)
            elif rec.ms < MID_MS:
                ms_item.setForeground(theme.COLOR_WARNING)
            else:
                ms_item.setForeground(theme.COLOR_FAILED)
            self.table.setItem(row, 3, ms_item)

            node_item = QTableWidgetItem(rec.node)
            node_item.setToolTip(rec.node)
            node_item.setForeground(theme.COLOR_MUTED)
            self.table.setItem(row, 4, node_item)

    def _update_stats(self) -> None:
        """刷新统计卡与汇总行（对应 updateSummary / updateSampleStats）。"""
        stats = summarize(self._engine.passing, self._engine.tested_count())

        self.stat_cards["cand"].set_value(str(len(self._engine.candidates)), "ACCENT")
        self.stat_cards["test"].set_value(str(self._engine.tested_count()), "BLUE")
        self.stat_cards["pass"].set_value(str(stats.passing), "GREEN")
        self.stat_cards["fast"].set_value(
            f"{stats.fastest_ms:.0f}" if stats.fastest_ms is not None else "--",
            "ORANGE",
        )

        self.rate_label.setText(
            f"存活率: {stats.success_rate:.1f}%" if stats.success_rate is not None else "存活率: --"
        )
        self.avg_label.setText(
            f"平均延迟: {stats.avg_ms:.0f}ms" if stats.avg_ms is not None else "平均延迟: --"
        )
        if stats.port_dist:
            self.port_label.setText(
                "端口分布: " + "  ".join(f"{p}×{n}" for p, n in stats.port_dist[:5])
            )
        else:
            self.port_label.setText("端口分布: --")

        self._refresh_buttons()

    # ==================================================================
    # 复制 / 下载 / 清空
    # ==================================================================
    def _copy_to_clipboard(self, text: str, success_msg: str) -> bool:
        """复制文本到剪贴板并给出反馈。

        Args:
            text: 要复制的内容。
            success_msg: 成功时显示的状态文字。

        Returns:
            是否成功。
        """
        if not text:
            return False
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return False
        clipboard.setText(text)
        self.status_label.setText(success_msg)
        return True

    def _on_copy_best(self) -> None:
        """一键复制最优 N 条（对应 copyBest）。"""
        n = self.keep_n_spin.value()
        nodes = self._engine.best_nodes(n)
        if not nodes:
            QMessageBox.information(self, "提示", "还没有可用节点，请先测速。")
            return
        done = self._copy_to_clipboard(
            "\n".join(nodes),
            f"已复制最优 {len(nodes)} 条，可在 V2RayN 从剪贴板导入",
        )
        if not done:
            QMessageBox.warning(self, "复制失败", "写入剪贴板失败。")

    def _on_copy_pass(self) -> None:
        """复制全部可用（对应 copyPass）。"""
        nodes = self._engine.all_nodes()
        if not nodes:
            QMessageBox.information(self, "提示", "还没有可用节点，请先测速。")
            return
        self._copy_to_clipboard("\n".join(nodes), f"已复制全部可用 {len(nodes)} 条")

    def _on_copy_ip(self) -> None:
        """复制 IP 列表（对应 copyIp）。"""
        ips = self._engine.all_ips()
        if not ips:
            QMessageBox.information(self, "提示", "还没有可用结果，请先测速。")
            return
        self._copy_to_clipboard("\n".join(ips), f"已复制 IP 列表（{len(ips)} 个）")

    def _on_download(self) -> None:
        """下载全部可用节点为 txt（对应 downloadNodes）。"""
        nodes = self._engine.all_nodes()
        if not nodes:
            QMessageBox.information(self, "提示", "还没有可用节点，请先测速。")
            return
        default_path = str(data_root() / "output" / "优选节点.txt")
        path, _ = QFileDialog.getSaveFileName(
            self, "保存节点列表", default_path, "文本文件 (*.txt);;所有文件 (*.*)"
        )
        if not path:
            return
        try:
            Path(path).write_text("\n".join(nodes), encoding="utf-8")
        except OSError as exc:
            QMessageBox.critical(self, "保存失败", f"写入文件失败：{exc}")
            logger.error("保存节点列表失败：%s", exc)
            return
        self.status_label.setText(f"已保存 {len(nodes)} 条节点到 {path}")
        QMessageBox.information(self, "保存成功", f"已保存 {len(nodes)} 条节点：\n{path}")

    def _on_clear(self) -> None:
        """清空结果与已测记录（对应 sampleClear）。"""
        if self._running:
            QMessageBox.information(self, "提示", "测速运行中，请先停止再清空。")
            return
        self._engine.clear()
        self.table.setRowCount(0)
        self.empty_label.setVisible(True)
        self.progress_bar.setValue(0, 0)
        self.status_label.setObjectName("Muted")
        self.status_label.setText("已清空结果与已测记录，可重新抽样测速")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        try:
            self._results_path().unlink(missing_ok=True)
        except OSError:
            pass
        self._update_stats()
        logger.info("用户清空了抽样结果")

    # ==================================================================
    # 生命周期
    # ==================================================================
    def shutdown(self) -> None:
        """窗口关闭时安全停止线程。"""
        worker = self._worker
        if worker is not None and worker.isRunning():
            worker.request_stop()
            worker.wait(3000)
        self._save_results()
        self._save_prefs()
