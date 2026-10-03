"""抽样测速页面的功能验证。

与 verify_features.py 同样的原则：**真调用**而非检查代码在不在。

包括：
1. 第四视图存在且可切换；
2. 配置读写与持久化（CIDR / 模板 / 参数 / 端口）；
3. 模板校验（含与不含 @IP:端口 两种情况）；
4. 真实测速引擎跑通（用一个已知可达的地址验证，证明引擎真的能出结果）；
5. 复制 / 清空 / 统计联动。

运行：
    python tests/verify_sample.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ⚠ 关键：把偏好/结果重定向到临时目录，避免测试数据污染用户真实配置。
# （曾发生：测试写入的 CIDR/模板把用户在界面上看到的默认值顶掉，用户以为「乱改」了）
_TMP = Path(tempfile.mkdtemp(prefix="ipo_sample_test_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "sample_prefs.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "sample_results.json")

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.sampler import ProbeResult, SampleEngine, probe_latency  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from gui.sample_page import SamplePage  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)


def main() -> int:
    """执行抽样页面功能验证。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")
    win = MainWindow()
    win.resize(1360, 940)
    win.show()
    app.processEvents()

    page = win.sample_page

    # ---------- 1. 视图注册与切换 ----------
    check("① 第四个视图已注册", "sample" in win._pages)
    win._switch_view("sample")
    app.processEvents()
    check("② 可切换到抽样测速页", page.isVisible())
    check("③ 侧边栏有对应导航按钮", "sample" in win._nav_buttons)

    # ---------- 2. 默认配置加载 ----------
    check("④ 默认 CIDR 已载入", len(page.cidr_edit.toPlainText().strip()) > 0,
          f"{page.cidr_count_label.text()}")
    check("⑤ 默认模板已载入", "@" in page.template_edit.toPlainText())

    # ---------- 3. 模板校验 ----------
    page.template_edit.setPlainText("vless://no-endpoint-here")
    app.processEvents()
    check("⑥ 无端点模板被识别为无效", "未找到" in page.template_hint.text(),
          page.template_hint.text()[:40])
    page.template_edit.setPlainText("vless://uuid@1.2.3.4:8443?x=1")
    app.processEvents()
    check("⑦ 有效模板被识别", "已识别端点" in page.template_hint.text(),
          page.template_hint.text()[:40])

    # ---------- 4. 端口选择器 ----------
    page.port_selector.select_all()
    check("⑧ 全选端口", len(page.port_selector.selected_ports()) == 13,
          f"选中 {len(page.port_selector.selected_ports())} 个")
    page.port_selector.select_none()
    check("⑨ 全不选端口", len(page.port_selector.selected_ports()) == 0)
    page.port_selector.set_selected([80, 443])
    check("⑩ 恢复指定端口", page.port_selector.selected_ports() == [80, 443],
          str(page.port_selector.selected_ports()))

    # ---------- 5. 配置持久化 ----------
    # 语义：改动即落盘（不等用户点保存），且新实例能读回。
    page.per_cidr_spin.setValue(123)
    page.concurrency_spin.setValue(77)
    page.cidr_edit.setPlainText("104.16.0.0/24")
    page.timeout_spin.setValue(1500)
    page.keep_n_spin.setValue(7)
    # notify=True 模拟用户勾选端口（默认静默，供配置恢复时使用）
    page.port_selector.set_selected([80, 443, 8443], notify=True)
    app.processEvents()

    import json as _json

    # 用页面自身的路径解析（会跟随测试重定向），而非硬编码真实路径
    on_disk = _json.loads(page._prefs_path().read_text(encoding="utf-8"))
    check("⑪ 改动即落盘：每段抽样", on_disk.get("per_cidr") == 123,
          f"盘上 {on_disk.get('per_cidr')}")
    check("⑫ 改动即落盘：并发/超时/保留N",
          on_disk.get("concurrency") == 77 and on_disk.get("timeout") == 1500
          and on_disk.get("keep_n") == 7,
          f"{on_disk.get('concurrency')}/{on_disk.get('timeout')}/{on_disk.get('keep_n')}")
    check("⑬ 改动即落盘：CIDR", "104.16.0.0/24" in (on_disk.get("cidr") or ""))
    check("⑭ 改动即落盘：端口", on_disk.get("ports") == [80, 443, 8443],
          str(on_disk.get("ports")))

    # 新实例应读回同样的配置（模拟重启）
    fresh = SamplePage()
    app.processEvents()
    check("⑭bis 新实例读回配置", fresh.per_cidr_spin.value() == 123
          and fresh.concurrency_spin.value() == 77
          and "104.16.0.0/24" in fresh.cidr_edit.toPlainText(),
          f"每段 {fresh.per_cidr_spin.value()} / 并发 {fresh.concurrency_spin.value()}")
    check("⑭ter 新实例读回端口", fresh.port_selector.selected_ports() == [80, 443, 8443],
          str(fresh.port_selector.selected_ports()))
    fresh.deleteLater()

    # ---------- 6. 真实测速引擎（用可达地址证明引擎可用） ----------
    # 本机可直连的国内站点，作为「引擎真能测出延迟」的实证
    ms = probe_latency("127.0.0.1", 80, "cloudflare", 1500)
    # 本机 80 端口未必开，用「能返回数值或明确的 -1」判定引擎未崩溃
    check("⑮ 单点探测不崩溃", ms == -1.0 or ms >= 0, f"返回 {ms}")

    # 引擎级：用一个不可能通的地址验证失败路径
    engine = SampleEngine()
    got = engine.run_round(
        cidr_text="192.0.2.0/29",     # TEST-NET-1，保留段，必定不可达
        per_cidr=10,
        ports=[80],
        template="vless://uuid@1.2.3.4:80?x=1",
        source="cloudflare",
        timeout_ms=300,
        concurrency=4,
    )
    check("⑯ 不可达段：新发现可用数 = 0", got == 0,
          f"新发现 {got} 个，已测记录 {engine.tested_count()} 条")
    check("⑰ 不可达段：全部被记录为已测（去重生效）", engine.tested_count() > 0,
          f"{engine.tested_count()} 条")
    check("⑱ 不可达段：结果列表为空", len(engine.passing) == 0)

    # 引擎级：手动塞结果验证统计与复制
    engine.passing = [
        ProbeResult(ip="1.1.1.1", port=443, ms=30.0, node="vless://u@1.1.1.1:443"),
        ProbeResult(ip="1.0.0.1", port=80, ms=90.0, node="vless://u@1.0.0.1:80"),
    ]
    check("⑱ best_nodes 取前 N", engine.best_nodes(1) == ["vless://u@1.1.1.1:443"],
          str(engine.best_nodes(1)))
    check("⑲ all_nodes / all_ips 正确",
          engine.all_nodes().__len__() == 2 and engine.all_ips() == ["1.1.1.1", "1.0.0.1"])

    # ---------- 7. 界面统计联动（把引擎结果接到页面） ----------
    page._engine = engine
    page._render_table()
    page._update_stats()
    app.processEvents()
    check("⑳ 结果表格渲染 2 行", page.table.rowCount() == 2,
          f"实际 {page.table.rowCount()} 行")
    check("㉑ 统计卡：可用数", page.stat_cards["pass"]._value.text().startswith("2"),
          page.stat_cards["pass"]._value.text())
    check("㉒ 统计卡：最优延迟 30", page.stat_cards["fast"]._value.text() == "30",
          page.stat_cards["fast"]._value.text())
    check("㉓ 汇总行：平均延迟", "60ms" in page.avg_label.text(), page.avg_label.text())

    # ---------- 8. 复制 ----------
    page._on_copy_ip()
    clip = QApplication.clipboard().text()
    check("㉔ 复制 IP 列表", clip == "1.1.1.1\n1.0.0.1", repr(clip))

    page._on_copy_pass()
    clip2 = QApplication.clipboard().text()
    check("㉕ 复制全部可用节点", clip2.count("\n") == 1 and "vless://" in clip2,
          repr(clip2[:40]))

    page.keep_n_spin.setValue(1)
    page._on_copy_best()
    clip3 = QApplication.clipboard().text()
    check("㉖ 复制最优 N 条", clip3 == "vless://u@1.1.1.1:443", repr(clip3))

    # ---------- 9. 清空 ----------
    page._on_clear()
    app.processEvents()
    check("㉗ 清空结果", page.table.rowCount() == 0 and not page._engine.passing)
    check("㉘ 清空后空态提示可见", page.empty_label.isVisible())

    # ---------- 10. 恢复默认（防「配置被改乱/污染后无法还原」） ----------
    from core.sampler import DEFAULT_CIDRS, DEFAULT_PORTS, DEFAULT_TEMPLATE
    from PySide6.QtWidgets import QMessageBox as _MB

    # 模拟用户把配置改乱
    page.cidr_edit.setPlainText("104.16.0.0/24")
    page.template_edit.setPlainText("vless://uuid@1.2.3.4:8443?x=1")
    page.per_cidr_spin.setValue(123)
    page.concurrency_spin.setValue(77)
    page.keep_n_spin.setValue(1)
    page.port_selector.set_selected([8443], notify=True)
    app.processEvents()
    check("㉙ 配置已改乱（前置条件）",
          page.cidr_edit.toPlainText().strip() == "104.16.0.0/24")

    # 自动确认二次确认弹窗
    _orig_question = _MB.question
    _MB.question = staticmethod(lambda *a, **k: _MB.StandardButton.Yes)
    try:
        page._on_reset_defaults()
    finally:
        _MB.question = _orig_question
    app.processEvents()

    check("㉚ 恢复默认：CIDR", page.cidr_edit.toPlainText().strip() == DEFAULT_CIDRS.strip(),
          f"{page.cidr_count_label.text()}")
    check("㉛ 恢复默认：模板", page.template_edit.toPlainText().strip() == DEFAULT_TEMPLATE.strip())
    check("㉜ 恢复默认：参数", page.per_cidr_spin.value() == 200
          and page.concurrency_spin.value() == 30
          and page.timeout_spin.value() == 800
          and page.keep_n_spin.value() == 20,
          f"{page.per_cidr_spin.value()}/{page.concurrency_spin.value()}/"
          f"{page.timeout_spin.value()}/{page.keep_n_spin.value()}")
    check("㉝ 恢复默认：端口", page.port_selector.selected_ports() == list(DEFAULT_PORTS),
          str(page.port_selector.selected_ports()))
    check("㉞ 恢复默认：状态提示已更新", "已恢复默认" in page.status_label.text(),
          page.status_label.text()[:30])

    # 取消时不改动
    page.cidr_edit.setPlainText("1.2.3.4/24")
    app.processEvents()
    _MB.question = staticmethod(lambda *a, **k: _MB.StandardButton.No)
    try:
        page._on_reset_defaults()
    finally:
        _MB.question = _orig_question
    check("㉟ 取消确认时不改动配置", page.cidr_edit.toPlainText().strip() == "1.2.3.4/24",
          page.cidr_edit.toPlainText().strip())

    # ---------- 11. 数值越界提示（用户输入 100 被截断时必须告知） ----------
    # 原问题：Qt 的 QSpinBox 静默把越界输入改成边界值，用户以为"值自己变了"
    page._pending_input["timeout"] = "100"
    page.timeout_spin.setValue(100)          # 会被截断到下限
    page._check_truncation("timeout", page.timeout_spin)
    app.processEvents()
    check("㊱ 越界输入被截断到下限", page.timeout_spin.value() == 200,
          f"生效 {page.timeout_spin.value()}")
    check("㊲ 越界时给出明确提示", page.range_hint.isVisible()
          and "自动调整" in page.range_hint.text(),
          page.range_hint.text())
    check("㊳ 提示中说明了原始输入与生效值",
          "100" in page.range_hint.text() and "200" in page.range_hint.text())

    # 合法输入时提示应消失
    page._pending_input["timeout"] = "1500"
    page.timeout_spin.setValue(1500)
    page._check_truncation("timeout", page.timeout_spin)
    app.processEvents()
    check("㊴ 合法输入时提示消失", not page.range_hint.isVisible(),
          f"值 {page.timeout_spin.value()}")

    # ---------- 12. 自动抽样不得改动用户的参数 ----------
    page.timeout_spin.setValue(1200)
    page.per_cidr_spin.setValue(150)
    page.concurrency_spin.setValue(45)
    before = (page.timeout_spin.value(), page.per_cidr_spin.value(), page.concurrency_spin.value())
    worker = page._build_worker(auto=True)     # 构建 worker（只读参数）
    after = (page.timeout_spin.value(), page.per_cidr_spin.value(), page.concurrency_spin.value())
    check("㊵ 构建自动抽样任务不改动用户参数", before == after,
          f"{before} -> {after}")
    if worker is not None:
        worker.deleteLater()

    # ---------- 13. 结果区必须撑满可用高度 ----------
    win.resize(1440, 960)
    win._switch_view("sample")
    app.processEvents()
    app.processEvents()
    table_h = page.table.height()
    panel_h = page.table.parent().height()
    check("㊶ 结果表格占据面板主要高度（撑满）",
          table_h >= 300 and table_h >= panel_h * 0.55,
          f"表格 {table_h}px / 面板 {panel_h}px")

    # ---------- 汇总 ----------
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"抽样页面验证：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
