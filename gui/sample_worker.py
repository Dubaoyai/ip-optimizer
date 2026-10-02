"""抽样测速的后台线程。

界面线程只负责显示，所有网络探测都在这里跑，保证窗口不卡死（与原项目
scan_worker / stability_worker 的做法一致）。
"""

from __future__ import annotations

import logging
from typing import List, Optional, Sequence

from PySide6.QtCore import QThread, Signal

from core.sampler import ProbeResult, SampleEngine, SampleStats, summarize
from utils.logger import get_logger

logger: logging.Logger = get_logger()


class SampleWorker(QThread):
    """单轮或自动连抽的后台线程。

    信号：
        progress(int, int)      —— 已测数 / 本轮总数
        passage_found(object)   —— 每发现一个可用节点（ProbeResult）
        round_finished(int)     —— 一轮结束，参数为本轮新测节点数
        finished_all(object)    —— 全部结束，参数为 SampleStats
        failed(str)             —— 出错（中文提示）
    """

    progress = Signal(int, int)
    passage_found = Signal(object)
    round_finished = Signal(int)
    finished_all = Signal(object)
    failed = Signal(str)

    def __init__(
        self,
        engine: SampleEngine,
        cidr_text: str,
        per_cidr: int,
        ports: Sequence[int],
        template: str,
        source: str,
        timeout_ms: int,
        concurrency: int,
        auto: bool = False,
        parent=None,
    ) -> None:
        """初始化测速线程。

        Args:
            engine: 抽样引擎（持有结果与去重集合）。
            cidr_text: CIDR 网段文本。
            per_cidr: 每段抽样数。
            ports: 待探测端口列表。
            template: 节点模板。
            source: 测速源键。
            timeout_ms: 超时毫秒。
            concurrency: 并发数。
            auto: True = 自动连抽模式（连续抽取直到覆盖完或用户停止）。
            parent: 父对象。
        """
        super().__init__(parent)
        self._engine = engine
        self._cidr_text = cidr_text
        self._per_cidr = per_cidr
        self._ports = list(ports)
        self._template = template
        self._source = source
        self._timeout_ms = timeout_ms
        self._concurrency = concurrency
        self._auto = auto
        self._rounds_done = 0

    # ------------------------------------------------------------------
    # 线程主体
    # ------------------------------------------------------------------
    def run(self) -> None:  # noqa: D102 (Qt 约定)
        try:
            idle_rounds = 0
            while True:
                fresh = self._engine.run_round(
                    cidr_text=self._cidr_text,
                    per_cidr=self._per_cidr,
                    ports=self._ports,
                    template=self._template,
                    source=self._source,
                    timeout_ms=self._timeout_ms,
                    concurrency=self._concurrency,
                    on_progress=self._emit_progress,
                    on_pass=self._emit_pass,
                )
                self._rounds_done += 1
                self.round_finished.emit(fresh)

                if not self._auto or self._engine.stopping:
                    break
                # 自动模式：连续两轮都没测到新节点，认为已覆盖完当前可抽库
                if fresh == 0:
                    idle_rounds += 1
                    if idle_rounds >= 2:
                        logger.info("自动抽样：连续两轮无新节点，判定已覆盖")
                        break
                else:
                    idle_rounds = 0

            stats = summarize(self._engine.passing, self._engine.tested_count())
            self.finished_all.emit(stats)
        except ValueError as exc:
            # 模板格式错误等可预期问题：中文提示，不崩溃
            logger.error("抽样测速失败：%s", exc)
            self.failed.emit(str(exc))
        except Exception as exc:  # 兜底：任何异常都要让界面知道
            logger.exception("抽样测速出现未预期错误")
            self.failed.emit(f"抽样测速出现错误：{exc}")

    # ------------------------------------------------------------------
    # 内部：转发引擎回调为 Qt 信号
    # ------------------------------------------------------------------
    def _emit_progress(self, done: int, total: int) -> None:
        """把引擎的进度回调转发为信号。"""
        self.progress.emit(done, total)

    def _emit_pass(self, result: ProbeResult) -> None:
        """把新发现的可用节点转发为信号。"""
        self.passage_found.emit(result)

    # ------------------------------------------------------------------
    # 对外
    # ------------------------------------------------------------------
    def request_stop(self) -> None:
        """请求停止（线程会在当前批次结束后退出）。"""
        self._engine.request_stop()

    @property
    def rounds_done(self) -> int:
        """已完成的轮数。"""
        return self._rounds_done


class SingleProbeWorker(QThread):
    """单独测一个 IP:端口（用于「测试模板」之类的即时验证）。

    信号：
        done(float, int) —— 延迟毫秒（-1 表示失败）与端口
    """

    done = Signal(float, int)

    def __init__(
        self, ip: str, port: int, source: str, timeout_ms: int, parent=None
    ) -> None:
        """初始化单点探测线程。

        Args:
            ip: 目标 IP。
            port: 目标端口。
            source: 测速源键。
            timeout_ms: 超时毫秒。
            parent: 父对象。
        """
        super().__init__(parent)
        self._ip = ip
        self._port = port
        self._source = source
        self._timeout_ms = timeout_ms

    def run(self) -> None:  # noqa: D102 (Qt 约定)
        from core.sampler import probe_latency

        ms = probe_latency(self._ip, self._port, self._source, self._timeout_ms)
        self.done.emit(ms, self._port)
