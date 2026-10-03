"""验证本轮全项目优化的新功能。

覆盖：
1. 结果表格列分组显示（默认核心列 / 展开全部列）
2. 工作台流程引导条（随数据状态推进）
3. 复制选中行（IP 与节点两种模式）
4. 清空结果的三选项确认（只清结果 / 完全重置 / 取消）

运行：
    python tests/verify_polish.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ipo_polish_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "p.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "r.json")

from PySide6.QtCore import QItemSelectionModel  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from core.ip_loader import IPEntry  # noqa: E402
from core.tcp_tester import TestResult  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)


def mk(ip: str, latency: int, port: int = 443) -> TestResult:
    """构造成功结果。"""
    base = TestResult(ip=ip, port=port, latency=latency, success=True, error=None)
    return replace(
        base, http_tested=True, http_status=200, http_latency=latency,
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

    # ==================== 1. 结果表格列分组 ====================
    table = win.result_table
    total = table.columnCount()
    visible = table.visible_columns_count()
    check("① 结果表总列数 = 17", total == 17, f"{total}")
    check("② 默认只显示核心列（< 全部）", visible < total, f"可见 {visible}/{total}")

    win.column_toggle_button.setChecked(True)
    app.processEvents()
    check("③ 展开后显示全部列", table.visible_columns_count() == total,
          f"{table.visible_columns_count()}")
    check("④ 展开后按钮文案变化", win.column_toggle_button.text() == "只显示核心列",
          win.column_toggle_button.text())

    win.column_toggle_button.setChecked(False)
    app.processEvents()
    check("⑤ 收起后回到核心列", table.visible_columns_count() == visible,
          f"{table.visible_columns_count()}")
    # 核心列必须包含关键信息
    core_names = [table.horizontalHeaderItem(i).text()
                  for i in range(total) if not table.isColumnHidden(i)]
    for need in ("排名", "IP", "TCP延迟", "下载速度", "综合评分", "状态"):
        check(f"⑥ 核心列包含「{need}」", need in core_names, str(core_names))

    # ==================== 2. 流程引导条 ====================
    win._switch_view("workbench")
    win._valid_entries = []
    win._refresh_stat_cards()
    app.processEvents()
    check("⑦ 无数据时引导指向第 ① 步", "①" in win.guide_hint.text(), win.guide_hint.text())

    win._valid_entries = [IPEntry(ip="104.16.0.1")]
    win._refresh_stat_cards()
    app.processEvents()
    check("⑧ 有 IP 后引导指向第 ② 步", "②" in win.guide_hint.text(), win.guide_hint.text())

    fake = [mk("104.16.0.1", 50), mk("104.16.0.2", 90, 80), mk("104.16.0.3", 150)]
    win._all_results = fake
    win._refresh_ranking_view()
    app.processEvents()
    check("⑨ 有结果后引导指向第 ③ 步", "③" in win.guide_hint.text(), win.guide_hint.text())

    # ==================== 3. 复制选中行 ====================
    win._switch_view("results")
    app.processEvents()
    table.clearSelection()
    sm = table.selectionModel()
    for row in (0, 2):
        sm.select(
            table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )
    app.processEvents()
    check("⑩ 多选 2 行成功", table.selected_rows_count() == 2,
          f"{table.selected_rows_count()}")
    check("⑪ 选中 IP 正确", set(table.selected_ips()) == {"104.16.0.1", "104.16.0.3"},
          str(table.selected_ips()))

    # 无模板 → 复制纯 IP
    win.result_template_edit.setText("")
    app.processEvents()
    win._on_copy_selected()
    clip = QApplication.clipboard().text()
    check("⑫ 无模板时复制纯 IP", clip.count("\n") == 1 and "vless" not in clip, repr(clip))

    # 有模板 → 复制节点
    tpl = ("vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443"
           "?encryption=none&security=none&type=ws&host=t.workers.dev#t")
    win.result_template_edit.setText(tpl)
    app.processEvents()
    win._on_copy_selected()
    clip2 = QApplication.clipboard().text()
    check("⑬ 有模板时复制节点链接",
          clip2.count("\n") == 1 and clip2.count("vless://") == 2 and "1.2.3.4" not in clip2,
          repr(clip2[:60]))
    check("⑭ 节点端口用实测值", ":443" in clip2, repr(clip2[:80]))

    # 单独验证「实测端口 80」会被正确带入（选中第 2 行，其端口为 80）
    table.clearSelection()
    sm.select(
        table.model().index(1, 0),
        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
    )
    app.processEvents()
    win._on_copy_selected()
    clip_port = QApplication.clipboard().text()
    check("⑭bis 端口 80 被正确代入节点",
          ":80" in clip_port and "104.16.0.2" in clip_port,
          repr(clip_port[:70]))

    # ==================== 4. 清空确认三选项 ====================
    # ⚠ Qt 会按按钮「角色」重排顺序，不可用索引定位；这里按**按钮文本**匹配。
    sp = win.sample_page
    from core.sampler import ProbeResult

    def fake_clear(button_keyword: str):
        """模拟用户点击了含某关键词的按钮；空字符串表示直接关闭对话框。

        Args:
            button_keyword: 按钮文本关键词；空串代表 pressed=None（关窗口/Esc）。
        """
        def _clicked(box):
            if not button_keyword:
                return None
            for b in box.buttons():
                if button_keyword in b.text():
                    return b
            return None

        QMessageBox.exec = lambda self: 0
        QMessageBox.clickedButton = _clicked

    def reset_mocks() -> None:
        QMessageBox.exec = orig_exec
        QMessageBox.clickedButton = orig_clicked

    orig_exec = QMessageBox.exec
    orig_clicked = QMessageBox.clickedButton

    def seed() -> None:
        """重置为「有 2 个结果 + 3 条去重记录」的初始状态。"""
        sp._engine.passing = [
            ProbeResult(ip="1.1.1.1", port=443, ms=30.0, node="n1"),
            ProbeResult(ip="1.1.1.2", port=443, ms=40.0, node="n2"),
        ]
        sp._engine.tested = {"n1", "n2", "n3"}

    # 4.1 关闭对话框（Esc）→ 必须什么都不做
    seed()
    fake_clear("")           # 返回 None，模拟关窗口
    try:
        sp._on_clear()
    finally:
        reset_mocks()
    check("⑮ 清空-关闭对话框：结果保留", len(sp._engine.passing) == 2,
          f"{len(sp._engine.passing)} 个")
    check("⑯ 清空-关闭对话框：去重记录保留", sp._engine.tested_count() == 3,
          f"{sp._engine.tested_count()} 条")

    # 4.2 点「取消」
    seed()
    fake_clear("取消")
    try:
        sp._on_clear()
    finally:
        reset_mocks()
    check("⑯bis 清空-点取消：数据不变",
          len(sp._engine.passing) == 2 and sp._engine.tested_count() == 3)

    # 4.3 只清结果 → 保留去重记录
    seed()
    fake_clear("只清结果")
    try:
        sp._on_clear()
    finally:
        reset_mocks()
    check("⑰ 只清结果：结果清空", len(sp._engine.passing) == 0)
    check("⑱ 只清结果：去重记录仍保留", sp._engine.tested_count() == 3,
          f"{sp._engine.tested_count()} 条")

    # 4.4 完全重置 → 都清
    seed()
    fake_clear("完全重置")
    try:
        sp._on_clear()
    finally:
        reset_mocks()
    check("⑲ 完全重置：结果与去重记录都清空",
          len(sp._engine.passing) == 0 and sp._engine.tested_count() == 0)

    # 4.5 空数据时不弹窗
    sp._engine.passing = []
    sp._engine.tested = set()
    called = {"n": 0}
    QMessageBox.exec = lambda self: called.__setitem__("n", called["n"] + 1)
    try:
        sp._on_clear()
    finally:
        QMessageBox.exec = orig_exec
    check("⑳ 无数据时不打扰用户（不弹窗）", called["n"] == 0, f"弹窗 {called['n']} 次")

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total_n = len(results)
    print(f"全项目优化验证：{passed}/{total_n} 通过")
    if passed < total_n:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
