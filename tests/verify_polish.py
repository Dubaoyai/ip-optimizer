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

    # ==================== 4. 导出选中行（2026-10-09 新增） ====================
    # 与「复制选中行」成对：此前只有复制没有导出，用户挑几行只能全量导出再手工删。
    # 这里用 monkeypatch 拦截 QFileDialog，避免弹真实保存框。
    import csv as _csv
    import tempfile
    from pathlib import Path as _Path

    from PySide6.QtWidgets import QFileDialog as _QFileDialog

    table.clearSelection()
    sm2 = table.selectionModel()
    for row in (0, 2):
        sm2.select(
            table.model().index(row, 0),
            QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
        )
    app.processEvents()

    _tmpdir = tempfile.TemporaryDirectory()
    _save_target = _Path(_tmpdir.name) / "选中导出.csv"
    _orig_get_save = _QFileDialog.getSaveFileName
    _orig_info = QMessageBox.information
    _orig_warning = QMessageBox.warning

    try:
        _QFileDialog.getSaveFileName = staticmethod(
            lambda *a, **k: (str(_save_target), "CSV 文件 (*.csv)")
        )
        QMessageBox.information = staticmethod(lambda *a, **k: None)
        QMessageBox.warning = staticmethod(lambda *a, **k: None)

        # 4.1 选中 2 行 → 导出
        win._on_export_selected()
        check("⑭-导出 文件已生成", _save_target.exists(), str(_save_target))

        if _save_target.exists():
            with _save_target.open(encoding="utf-8-sig", newline="") as fh:
                rows = list(_csv.reader(fh))
            check("⑭-导出 行数 == 选中数 + 表头", len(rows) == 3, f"{len(rows)} 行")
            check("⑭-导出 含选中 IP",
                  {rows[1][1], rows[2][1]} == {"104.16.0.1", "104.16.0.3"},
                  str([rows[1][1], rows[2][1]]))
            check("⑭-导出 未夹带未选中行",
                  "104.16.0.2" not in {rows[1][1], rows[2][1]},
                  str(rows))

        # 4.2 未选中任何行 → 不生成文件、不报错
        _save_target.unlink(missing_ok=True)
        table.clearSelection()
        app.processEvents()
        win._on_export_selected()
        check("⑭-导出 空选中时不生成文件", not _save_target.exists())

        # 4.3 按钮存在且已接入启用清单（防止「加了按钮永远是灰的」）
        check("⑭-导出 按钮已创建", hasattr(win, "export_selected_button"))
        check("⑭-导出 按钮在启用清单内",
              win.export_selected_button.isEnabled() ==
              win.copy_selected_button.isEnabled(),
              f"export={win.export_selected_button.isEnabled()} "
              f"copy={win.copy_selected_button.isEnabled()}")
    finally:
        _QFileDialog.getSaveFileName = _orig_get_save
        QMessageBox.information = _orig_info
        QMessageBox.warning = _orig_warning
        _tmpdir.cleanup()

    # ==================== 5. 清空确认三选项 ====================
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

    # ==================== 6. 侧边栏展开 / 收起（V1.5） ====================
    # 用户需求：「左侧栏可以收缩」。
    # 关键断言：min 与 max 必须同步变化 —— 只改一个会导致
    #   只改 max ⇒ 收起时 min 锁住宽度（收不动）；
    #   只改 min ⇒ 展开时卡在内容自然宽度（实测只有 207px，达不到 240）。
    _orig_anim = theme.SIDEBAR_ANIM_MS
    theme.SIDEBAR_ANIM_MS = 0      # 关动画，便于同步断言
    try:
        side = win._sidebar
        toggle = win.sidebar_toggle_button

        # 6.1 初始应为展开
        win.set_sidebar_expanded(True)
        app.processEvents()
        check("㉑ 侧边栏初始展开宽度正确",
              side.width() == theme.SIDEBAR_WIDTH,
              f"{side.width()} (期望 {theme.SIDEBAR_WIDTH})")

        # 6.2 点击按钮 → 收起
        toggle.click()
        app.processEvents()
        check("㉒ 点击按钮后侧边栏收起", side.width() == 0, f"{side.width()}")

        # 6.3 按钮必须仍在可见区（否则收起后无法再展开 —— 经典坑）
        check("㉓ 收起后切换按钮仍可见（能再展开）", toggle.isVisible())
        # 且必须在**窗口最左侧**（用户预期位置；曾误放在顶栏导致被挤到 x=260）
        btn_x = toggle.mapTo(win, toggle.rect().topLeft()).x()
        check("㉔ 切换按钮位于窗口最左（x < 40）", btn_x < 40, f"x={btn_x}")

        # 6.4 按钮必须有足够对比度（曾因颜色过淡导致用户找不到入口）
        check("㉕ 切换按钮尺寸足够可点（≥32x26）",
              toggle.width() >= 32 and toggle.height() >= 26,
              f"{toggle.width()}x{toggle.height()}")

        # 6.5 再点 → 展开，且宽度必须精确回到 240（防「卡在内容自然宽度」）
        toggle.click()
        app.processEvents()
        check("㉖ 再次点击后完全展开（min/max 同步）",
              side.width() == theme.SIDEBAR_WIDTH,
              f"{side.width()} (期望 {theme.SIDEBAR_WIDTH})")

        # 6.6 展开标志与提示文字一致
        check("㉗ 展开标志与提示文字一致",
              win._sidebar_expanded and "收起" in toggle.toolTip(),
              f"expanded={win._sidebar_expanded} tip={toggle.toolTip()!r}")
    finally:
        theme.SIDEBAR_ANIM_MS = _orig_anim

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
