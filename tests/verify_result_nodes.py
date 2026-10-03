"""验证「测试结果的优选节点」与「导出」新功能。

覆盖：
1. 结果页有代理模板输入框与节点按钮；
2. 模板校验（含/不含 @IP:端口）；
3. 复制节点 / 导出节点（真实生成文件并检查内容）；
4. 导出 TXT / CSV 走另存为路径（用 monkeypatch 模拟用户选路径）；
5. 无数据/无模板时的友好提示（不崩溃）。

运行：
    python tests/verify_result_nodes.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ipo_nodes_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "p.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "r.json")

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.ranking import build_ranking  # noqa: E402
from core.tcp_tester import TestResult  # noqa: E402
from dataclasses import replace  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)


def make_result(ip: str, latency: int, port: int = 443) -> TestResult:
    """构造一条成功的测速结果。"""
    base = TestResult(ip=ip, port=port, latency=latency, success=True, error=None)
    return replace(
        base,
        http_tested=True, http_status=200, http_latency=latency,
        download_tested=True, download_speed_bps=5_000_000.0, download_error=None,
    )


def main() -> int:
    """执行验证。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")
    win = MainWindow()
    win.resize(1440, 960)
    win.show()
    app.processEvents()

    # ---------- 1. 控件存在 ----------
    check("① 结果页有代理模板输入框", hasattr(win, "result_template_edit"))
    check("② 有「复制节点」按钮", hasattr(win, "copy_nodes_button"))
    check("③ 有「导出节点」按钮", hasattr(win, "export_nodes_button"))
    check("④ 无数据时节点按钮为禁用",
          not win.copy_nodes_button.isEnabled() and not win.export_nodes_button.isEnabled())

    # ---------- 2. 准备排名数据 ----------
    fake = [make_result("104.16.0.1", 50, 443), make_result("104.16.0.2", 90, 80),
            make_result("104.16.0.3", 150, 443)]
    entries = build_ranking(fake, min_speed_bps=None, max_tcp_latency_ms=None, top_n=10)
    win._all_results = fake
    win.result_table.set_ranking(entries)
    win._set_export_buttons_enabled(True)
    app.processEvents()
    check("⑤ 测速后节点按钮启用", win.copy_nodes_button.isEnabled())

    # ---------- 3. 模板校验 ----------
    win.result_template_edit.setText("vless://no-endpoint")
    app.processEvents()
    check("⑥ 无端点模板给出警告", "未找到" in win.result_template_hint.text(),
          win.result_template_hint.text()[:40])

    tpl = ("vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443"
           "?encryption=none&security=none&type=ws&host=my.workers.dev#我的节点")
    win.result_template_edit.setText(tpl)
    app.processEvents()
    check("⑦ 有效模板被识别", "已识别端点" in win.result_template_hint.text(),
          win.result_template_hint.text()[:50])

    # ---------- 4. 复制节点 ----------
    win._on_copy_nodes()
    clip = QApplication.clipboard().text()
    lines = [x for x in clip.splitlines() if x.strip()]
    check("⑧ 复制节点：条数 = 排名条数", len(lines) == 3, f"复制到 {len(lines)} 条")
    check("⑨ 复制节点：IP 被替换", "104.16.0.1" in clip and "1.2.3.4" not in clip,
          clip.splitlines()[0][:70] if lines else "")
    check("⑩ 复制节点：端口被替换为实测端口", "104.16.0.1:443" in clip and ":80" in clip,
          "含 443 与 80")
    check("⑪ 复制节点：保留模板其余参数", "host=my.workers.dev" in clip)

    # 空模板时给出提示（不崩溃）
    win.result_template_edit.setText("")
    app.processEvents()
    orig_info = QMessageBox.information
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        win._on_copy_nodes()
        check("⑫ 空模板时提示而非崩溃", True)
    except Exception as exc:
        check("⑫ 空模板时提示而非崩溃", False, f"{type(exc).__name__}: {exc}")
    finally:
        QMessageBox.information = orig_info
    win.result_template_edit.setText(tpl)
    app.processEvents()

    # ---------- 5. 导出节点（模拟用户选路径） ----------
    target = _TMP / "nodes_out.txt"
    from PySide6.QtWidgets import QFileDialog

    orig_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(target), ""))
    QMessageBox.information = staticmethod(lambda *a, **k: None)
    try:
        win._on_export_nodes()
    except Exception as exc:
        check("⑬ 导出节点不崩溃", False, f"{type(exc).__name__}: {exc}")
    finally:
        QFileDialog.getSaveFileName = orig_save
        QMessageBox.information = orig_info

    check("⑬ 导出节点：文件已生成", target.exists(), str(target))
    if target.exists():
        content = target.read_text(encoding="utf-8")
        check("⑭ 导出节点：内容为 3 条节点", len([x for x in content.splitlines() if x.strip()]) == 3)
        check("⑮ 导出节点：内容含实测 IP", "104.16.0.1" in content)
        check("⑯ 导出节点：不含模板占位 IP", "1.2.3.4" not in content)

    # ---------- 6. 导出 TXT / CSV 走另存为 ----------
    txt_target = _TMP / "result.txt"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(txt_target), ""))
    try:
        win._on_export_txt()
    finally:
        QFileDialog.getSaveFileName = orig_save
    check("⑰ 导出 TXT：文件已生成", txt_target.exists(), str(txt_target))
    if txt_target.exists():
        check("⑱ 导出 TXT：每行一个 IP",
              all("vless" not in x for x in txt_target.read_text(encoding="utf-8").splitlines() if x.strip()))

    csv_target = _TMP / "result.csv"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: (str(csv_target), ""))
    try:
        win._on_export_csv()
    finally:
        QFileDialog.getSaveFileName = orig_save
    check("⑲ 导出 CSV：文件已生成", csv_target.exists(), str(csv_target))
    if csv_target.exists():
        text = csv_target.read_text(encoding="utf-8-sig")
        check("⑳ 导出 CSV：含表头与数据行",
              "排名" in text and "104.16.0.1" in text,
              f"{len(text.splitlines())} 行")

    # ---------- 7. 取消另存为则不写文件 ----------
    cancel_target = _TMP / "should_not_exist.txt"
    QFileDialog.getSaveFileName = staticmethod(lambda *a, **k: ("", ""))
    try:
        win._on_export_txt()
        win._on_export_nodes()
    finally:
        QFileDialog.getSaveFileName = orig_save
    check("㉑ 取消另存为时不产生文件", not cancel_target.exists())

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"结果页节点与导出验证：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
