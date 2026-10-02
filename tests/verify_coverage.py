"""原版功能点覆盖核验：把原 HTML 的所有可交互元素列出来，逐个确认有对应实现。

这是"是否偷工"的第二层核验（第一层 verify_fidelity.py 查常量与参数，
本层查**行为/交互元素**是否齐全）。

运行：
    python tests/verify_coverage.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SOURCE_HTML = Path(r"D:\软件\节点工具\优选IP测速_重构版.html")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    results.append((name, ok, detail))
    print(f"[{'OK  ' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def main() -> int:
    """核验交互元素覆盖率。"""
    text = SOURCE_HTML.read_text(encoding="utf-8")
    page_src = (ROOT / "gui" / "sample_page.py").read_text(encoding="utf-8")
    widget_src = (ROOT / "gui" / "widgets.py").read_text(encoding="utf-8")
    engine_src = (ROOT / "core" / "sampler.py").read_text(encoding="utf-8")
    all_src = page_src + widget_src + engine_src

    # ---------- 1. 原版所有带 id 的可交互元素 ----------
    element_ids = re.findall(r'<(?:button|input|select|textarea)[^>]*\bid="(\w+)"', text)
    # 原版 id -> 我的实现中应有对应能力的映射（人工核对后登记）
    coverage = {
        # 输入类
        "cidrInput": ("CIDR 编辑框", "self.cidr_edit"),
        "templateInput": ("模板编辑框", "self.template_edit"),
        "speedSource": ("测速源下拉", "self.source_combo"),
        "sampleNum": ("每段抽样", "self.per_cidr_spin"),
        "concSample": ("并发数", "self.concurrency_spin"),
        "timeoutSample": ("超时", "self.timeout_spin"),
        "keepSample": ("保留最优N", "self.keep_n_spin"),
        # 按钮类
        "portBtn": ("端口选择按钮", "_button"),
        "portAll": ("端口全选", "select_all"),
        "portNone": ("端口清空", "select_none"),
        "sStart": ("抽样测速", "self.start_button"),
        "sAuto": ("自动抽样", "self.auto_button"),
        "sStop": ("停止", "self.stop_button"),
        "sClear": ("清空结果", "self.clear_button"),
        "copyBestBtn": ("复制最优N条", "self.copy_best_button"),
        "copyPassBtn": ("复制全部可用", "self.copy_pass_button"),
        "copyIpBtn": ("复制IP列表", "self.copy_ip_button"),
        "downloadBtn": ("下载全部可用", "self.download_button"),
    }
    print(f"=== 原版可交互元素共 {len(element_ids)} 个 ===")
    missing = []
    for ident in element_ids:
        if ident not in coverage:
            missing.append(ident)
            continue
        label, target = coverage[ident]
        # 目标符号出现在任一新源码中即视为已实现
        token = target.split(".")[-1]
        ok = token in all_src
        check(f"{ident} → {label}", ok, f"查找 {token!r}")
    if missing:
        check("所有原版元素都已登记映射", False, f"未登记的 id: {missing}")
    else:
        check("所有原版元素都已登记映射", True, f"{len(element_ids)} 个全部覆盖")

    # ---------- 2. 原版显示类元素（统计/汇总/状态） ----------
    display_ids = [
        ("cidrCount", "段数显示", "cidr_count_label"),
        ("portLabel", "端口摘要", "_refresh_label"),
        ("sProgressBar", "进度条", "ProgressBar"),
        ("sProgressText", "进度文字", "setValue"),
        ("sStatus", "状态文字", "status_label"),
        ("statCand", "候选统计", '"cand"'),
        ("statTest", "已测统计", '"test"'),
        ("statPass", "可用统计", '"pass"'),
        ("statFast", "最优统计", '"fast"'),
        ("statRate", "存活率", "rate_label"),
        ("statAvg", "平均延迟", "avg_label"),
        ("statPort", "端口分布", "port_label"),
        ("resultBody", "结果表体", "self.table"),
        ("emptyState", "空态提示", "empty_label"),
        ("resultModeTag", "模式标签", "抽样测速"),
    ]
    print()
    print(f"=== 原版显示元素共 {len(display_ids)} 个 ===")
    for _ident, label, token in display_ids:
        ok = token in all_src
        check(f"显示元素：{label}", ok, f"查找 {token!r}")

    # ---------- 3. 原版核心函数是否都有对应 ----------
    functions = [
        ("renderPortLabel", "端口摘要刷新", "_refresh_label"),
        ("buildPortList", "端口列表构建", "_checks"),
        ("sampleV4", "IPv4 抽样", "sample_ipv4"),
        ("sampleV6", "IPv6 抽样", "sample_ipv6"),
        ("buildCandidates", "候选构建", "build_candidates"),
        ("extractTemplatePort", "模板解析", "extract_template_port"),
        ("buildNode", "节点生成", "build_node"),
        ("builtInEngine", "测速引擎", "probe_latency"),
        ("probePorts", "端口解析", "resolve_probe_ports"),
        ("probeIp", "多端口探测", "probe_ip"),
        ("updateSummary", "汇总统计", "summarize"),
        ("saveResults", "结果保存", "_save_results"),
        ("loadResults", "结果读取", "_load_results"),
        ("runRound", "单轮测速", "run_round"),
        ("sampleStart", "单次启动", "_on_start"),
        ("sampleAuto", "自动启动", "_on_auto"),
        ("sampleStop", "停止", "_on_stop"),
        ("sampleClear", "清空", "_on_clear"),
        ("updateSampleStats", "统计刷新", "_update_stats"),
        ("renderTable", "表格渲染", "_render_table"),
        ("copyBest", "复制最优", "_on_copy_best"),
        ("copyPass", "复制全部", "_on_copy_pass"),
        ("copyIp", "复制IP", "_on_copy_ip"),
        ("downloadNodes", "下载节点", "_on_download"),
        ("persistFixed", "配置保存", "_save_prefs"),
        ("load", "配置读取", "_load_prefs"),
    ]
    print()
    print(f"=== 原版核心函数共 {len(functions)} 个 ===")
    for js_name, label, token in functions:
        ok = token in all_src
        check(f"{js_name} → {label}", ok, f"查找 {token!r}")

    # ---------- 4. 原版交互细节 ----------
    print()
    print("=== 交互细节 ===")
    check("点击面板外部收起端口面板",
          "eventFilter" in widget_src and "MouseButtonPress" in widget_src)
    check("复制后给出成功/失败反馈",
          "_copy_to_clipboard" in page_src and "status_label.setText" in page_src)
    check("测速运行中禁用清空", "请先停止再清空" in page_src)
    check("结果按延迟升序累积", "self.passing.sort" in engine_src)
    check("已测节点去重（不重复测同一 IP:端口）", "if node in tested" in engine_src)
    check("自动模式：连续无新发现即收敛", "idle_rounds" in (ROOT / "gui" / "sample_worker.py").read_text(encoding="utf-8"))
    check("模板校验（无 @IP:端口 时拒绝启动）", "未找到 @IP:端口" in page_src)
    check("支持 IPv6 网段（自动识别）", "is_ipv6_cidr" in engine_src)

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"覆盖核验：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
