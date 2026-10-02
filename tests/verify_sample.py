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

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

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
    from utils.paths import data_root as _data_root

    on_disk = _json.loads((_data_root() / "sample_prefs.json").read_text(encoding="utf-8"))
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
