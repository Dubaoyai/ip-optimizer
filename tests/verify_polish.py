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
    # 用 classmethod 包装后，测试只需 mock ClearChoiceDialog.ask 一个方法，
    # 不再触碰 QMessageBox.exec / clickedButton 等内部细节
    # （此前 36 处脆弱 mock 导致「一改 UI 就要改一批测试」）。
    sp = win.sample_page
    from core.sampler import ProbeResult
    from gui.sample_page import ClearChoiceDialog

    _orig_ask = ClearChoiceDialog.ask

    def seed() -> None:
        """重置为「2 个结果 + 3 条去重记录」。"""
        sp._engine.passing = [
            ProbeResult(ip="1.1.1.1", port=443, ms=30.0, node="n1"),
            ProbeResult(ip="1.1.1.2", port=443, ms=40.0, node="n2"),
        ]
        sp._engine.tested = {"n1", "n2", "n3"}

    def choose(choice: str) -> None:
        """模拟用户在清空对话框里做出某种选择。"""
        ClearChoiceDialog.ask = classmethod(
            lambda cls, c, t, parent=None, _c=choice: _c
        )

    try:
        # 4.1 取消（含 Esc / 关窗口）
        seed(); choose(ClearChoiceDialog.CANCEL); sp._on_clear()
        check("⑮ 清空-取消：结果保留", len(sp._engine.passing) == 2,
              f"{len(sp._engine.passing)} 个")
        check("⑯ 清空-取消：去重记录保留", sp._engine.tested_count() == 3,
              f"{sp._engine.tested_count()} 条")

        # 4.2 只清结果
        seed(); choose(ClearChoiceDialog.KEEP); sp._on_clear()
        check("⑰ 只清结果：结果清空", len(sp._engine.passing) == 0)
        check("⑱ 只清结果：去重记录仍保留", sp._engine.tested_count() == 3,
              f"{sp._engine.tested_count()} 条")

        # 4.3 完全重置
        seed(); choose(ClearChoiceDialog.FULL); sp._on_clear()
        check("⑲ 完全重置：结果与去重记录都清空",
              len(sp._engine.passing) == 0 and sp._engine.tested_count() == 0)

        # 4.4 未知返回值 → 视为取消，绝不误删
        seed(); choose("something-weird"); sp._on_clear()
        check("⑲bis 未知返回值按取消处理（防误删）",
              len(sp._engine.passing) == 2 and sp._engine.tested_count() == 3)
    finally:
        ClearChoiceDialog.ask = _orig_ask

    # 4.5 空数据时不弹窗
    sp._engine.passing = []
    sp._engine.tested = set()
    asked = {"n": 0}
    ClearChoiceDialog.ask = classmethod(
        lambda cls, c, t, parent=None: asked.__setitem__("n", asked["n"] + 1) or cls.CANCEL
    )
    try:
        sp._on_clear()
    finally:
        ClearChoiceDialog.ask = _orig_ask
    check("⑳ 无数据时不打扰用户（不弹窗）", asked["n"] == 0, f"弹窗 {asked['n']} 次")

    # ---------- 汇总 ----------
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
