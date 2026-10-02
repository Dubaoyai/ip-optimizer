"""功能完整性验证：逐项确认重构后所有原有功能仍然可用。

验证方式不是"看代码在不在"，而是**真的调用一遍**：
1. 粘贴导入 IP（走真实校验链路）
2. 从文件导入
3. 统计卡片联动
4. 测速设置控件读写
5. HTTP / 下载开关联动
6. 排名计算 + 表格写入 + 摘要
7. 复制 TOP N（真实读剪贴板）
8. 导出 TXT / CSV / 稳定性 TXT / 稳定性 CSV（真实写文件）
9. 三个视图切换
10. 结果表格清空

运行：
    python tests/verify_features.py
退出码：0 = 全部通过；1 = 有失败项。
"""

from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from core.ip_validator import import_from_file, import_from_text  # noqa: E402
from core.ranking import build_ranking  # noqa: E402
from core.stability import StabilityData  # noqa: E402
from core.tcp_tester import TestResult  # noqa: E402
from core.ranking import build_final_ranking  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录一条检查结果并即时打印。"""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)


def make_result(ip: str, latency: int, success: bool = True) -> TestResult:
    """构造一条测速结果（带 HTTP 与下载字段，模拟完整三级测速）。

    TestResult 是 frozen dataclass，字段只能用 dataclasses.replace 赋值。
    """
    base = TestResult(
        ip=ip,
        port=443,
        latency=latency if success else None,
        success=success,
        error=None if success else "超时",
    )
    return replace(
        base,
        http_tested=True,
        http_status=200 if success else None,
        http_latency=latency if success else None,
        download_tested=True,
        download_speed_bps=(5 * 1024 * 1024 - latency * 1024) if success else None,
        download_error=None if success else "下载失败",
    )


def main() -> int:
    """执行全部功能检查。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)
    theme.apply_theme(app)
    win = MainWindow()
    win.resize(1280, 900)
    win.show()
    app.processEvents()

    # ---------- 1. 粘贴导入 IP ----------
    text = "104.16.0.1\n104.16.0.2:443\n8.8.8.8\n1.1.1.1\n无效内容\n104.16.0.1"
    win.ip_panel.ip_text_edit.setPlainText(text)
    outcome = import_from_text(text)
    win._valid_entries = outcome.valid_entries
    win.ip_panel._valid_entries = outcome.valid_entries
    win.ip_panel._update_statistics(outcome.summary)
    check("① 粘贴导入 IP", outcome.summary.valid_count >= 3,
          f"有效 {outcome.summary.valid_count} / 读取 {outcome.summary.total_lines}")
    check("② 自动去重", outcome.summary.duplicate_count == 1,
          f"重复数 = {outcome.summary.duplicate_count}")
    check("③ 非法内容被拦截", outcome.summary.invalid_count >= 1,
          f"无效 IP = {outcome.summary.invalid_count}（「无效内容」这行被正确拦截）")

    # ---------- 2. 从文件导入 ----------
    sample = ROOT / "sample_ips.txt"
    if sample.exists():
        fout = import_from_file(str(sample))
        check("④ 文件导入 IP", fout.summary.valid_count > 0,
              f"sample_ips.txt 有效 {fout.summary.valid_count} 条")
    else:
        check("④ 文件导入 IP", False, "sample_ips.txt 缺失")

    # ---------- 3. 统计卡片联动 ----------
    win._refresh_stat_cards()
    shown = win.stat_cards["ip"]._value.text()
    check("⑤ 统计卡片随数据更新", shown.isdigit() and int(shown) > 0, f"候选 IP 卡片 = {shown}")

    # ---------- 4. 测速设置控件读写 ----------
    win.port_spin.setValue(8443)
    win.concurrency_spin.setValue(100)
    win.timeout_spin.setValue(2000)
    ok_setting = (win.port_spin.value() == 8443 and win.concurrency_spin.value() == 100
                  and win.timeout_spin.value() == 2000)
    check("⑥ 测速设置可读写", ok_setting, "端口/并发/超时写入成功")

    win.download_size_combo.setCurrentIndex(3)
    check("⑦ 下载大小下拉可用", win.download_size_combo.currentData() == 2 * 1024 * 1024,
          f"选中 = {win.download_size_combo.currentData()} 字节")

    # ---------- 5. 开关联动 ----------
    win.http_checkbox.setChecked(False)
    app.processEvents()
    check("⑧ HTTP 开关联动", not win.http_timeout_spin.isEnabled(), "关闭后超时框禁用")
    win.http_checkbox.setChecked(True)
    app.processEvents()
    check("⑨ HTTP 开关恢复", win.http_timeout_spin.isEnabled(), "重开后超时框可用")

    # ---------- 6. 排名 / 表格 / 摘要 ----------
    fake = [make_result("10.0.0.1", 50), make_result("10.0.0.2", 150), make_result("10.0.0.3", 0, False)]
    win._all_results = fake
    entries = build_ranking(fake, min_speed_bps=None, max_tcp_latency_ms=None, top_n=10)
    win.result_table.set_ranking(entries)
    win._update_summary_text(entries)
    win._refresh_stat_cards()
    check("⑩ 排名计算 + 表格写入", win.result_table.rowCount() >= 3,
          f"表格 {win.result_table.rowCount()} 行")
    check("⑪ 结果摘要生成", "有效IP" in win.result_summary_label.text(),
          win.result_summary_label.text()[:50])
    check("⑫ 速度/延迟卡片联动", win.stat_cards["speed"]._value.text() != "—",
          f"最快速度 = {win.stat_cards['speed']._value.text()} MB/s")

    # ---------- 7. 复制 TOP ----------
    win._copy_top(2)
    clip = QApplication.clipboard().text()
    check("⑬ 复制 TOP2 到剪贴板", "10.0.0.1" in clip and clip.count("\n") == 1, repr(clip))

    # ---------- 8. 导出四种文件 ----------
    from utils.export import export_csv, export_stable_csv, export_stable_txt, export_txt

    try:
        p1 = export_txt(win.result_table.rank_entries, top_n=100)
        check("⑭ 导出 TOP TXT", Path(p1).exists(), str(p1))
    except Exception as exc:
        check("⑭ 导出 TOP TXT", False, f"{type(exc).__name__}: {exc}")

    try:
        p2 = export_csv(win.result_table.rank_entries)
        check("⑮ 导出完整 CSV", Path(p2).exists(), str(p2))
    except Exception as exc:
        check("⑮ 导出完整 CSV", False, f"{type(exc).__name__}: {exc}")

    # 稳定性导出需要先有最终排名
    stab_map = {
        "10.0.0.1": StabilityData(
            ip="10.0.0.1",
            port=443,
            rounds=5,
            tcp_latencies=[50, 51, 49, 52, 50],
            http_latencies=[60, 61, 59, 62, 60],
            download_speeds=[5_000_000.0] * 5,
            tcp_total=5,
            tcp_success=5,
            http_total=5,
            http_success=5,
            download_total=5,
            download_success=5,
        )
    }
    final = build_final_ranking(win.result_table.rank_entries, stab_map)
    if final:
        win.result_table.set_final_ranking(final)
        try:
            p3 = export_stable_txt(final, top_n=100)
            check("⑯ 导出稳定 TOP TXT", Path(p3).exists(), str(p3))
        except Exception as exc:
            check("⑯ 导出稳定 TOP TXT", False, f"{type(exc).__name__}: {exc}")
        try:
            p4 = export_stable_csv(final)
            check("⑰ 导出稳定性 CSV", Path(p4).exists(), str(p4))
        except Exception as exc:
            check("⑰ 导出稳定性 CSV", False, f"{type(exc).__name__}: {exc}")
    else:
        check("⑯ 导出稳定 TOP TXT", False, "最终排名为空，无法测试导出")

    # ---------- 9. 视图切换 ----------
    ok_views = True
    for key in ("workbench", "results", "stability"):
        win._switch_view(key)
        app.processEvents()
        if not win._pages[key].isVisible():
            ok_views = False
    check("⑱ 三个视图可切换", ok_views, "工作台/测试结果/稳定性复测 均能显示")

    # ---------- 10. 表格清空 ----------
    win.result_table.clear_results()
    check("⑲ 表格可清空", win.result_table.rowCount() == 0, "行数归零")

    # ---------- 汇总 ----------
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"\n{'=' * 46}")
    print(f"功能验证汇总：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name} {detail}")
    print("=" * 46, flush=True)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
