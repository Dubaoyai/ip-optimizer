"""用户体验走查：模拟真实使用路径，找出「不合人性」的地方。

检查思路：不看代码好不好，而是问「用户要做到某件事，需要几步 / 会不会困惑」。

覆盖：
1. 首次打开：用户知道该干什么吗？（空态是否有引导）
2. 各页面：有没有解释了用途、下一步动作是否明确
3. 按钮文案：是否说人话、是否前后一致
4. 危险操作：是否有确认 / 是否可撤销
5. 长任务：是否有进度 / 能否中止
6. 反馈：成功/失败是否都有明确提示
7. 信息显示：关键数据是否一眼可见

运行：
    python tools/audit_ux.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ipo_ux_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "p.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "r.json")

from PySide6.QtWidgets import QApplication, QPushButton, QLabel, QComboBox, QSpinBox  # noqa: E402
from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QCheckBox, QTableWidget  # noqa: E402

from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

issues: list[tuple[str, str, str]] = []   # (严重度, 位置, 描述)


def add(sev: str, where: str, desc: str) -> None:
    """记录一条体验问题。"""
    issues.append((sev, where, desc))


def walk(widget, depth: int = 0):
    """递归遍历控件的可见文本。"""
    yield widget
    for child in widget.findChildren(object):
        if isinstance(child, (QPushButton, QLabel, QComboBox, QSpinBox,
                              QLineEdit, QPlainTextEdit, QCheckBox)):
            yield child
        if depth < 6:
            yield from walk(child, depth + 1)


def main() -> int:
    """执行体验走查。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")
    win = MainWindow()
    win.resize(1440, 960)
    win.show()
    app.processEvents()

    print("=" * 74)
    print("体验走查：模拟真实使用路径")
    print("=" * 74)

    # ---------- 1. 首次打开是否有引导 ----------
    print("\n【1】首次打开：用户知道该干什么吗")
    win._switch_view("workbench")
    app.processEvents()
    texts = [getattr(w, "text", lambda: "")() or "" for w in walk(win)]
    has_guide = any("导入" in t and ("请" in t or "提示" in t or "步骤" in t) for t in texts)
    print(f"  空态引导存在：{has_guide}")
    if not has_guide:
        add("中", "工作台", "首次打开缺少「第一步该做什么」的引导文案")
    else:
        sample = next(t for t in texts if "导入" in t and len(t) < 60)
        print(f"  示例文案：{sample}")

    # ---------- 2. 按钮文案 ----------
    print("\n【2】按钮文案检查")
    buttons = [b.text() for b in win.findChildren(QPushButton) if b.text().strip()]
    print(f"  按钮总数：{len(buttons)}")
    vague = [b for b in buttons if b in ("确定", "取消", "OK", "是", "否")]
    if vague:
        print(f"  ⚠ 含义模糊的按钮：{vague}")
    else:
        print("  无含义模糊的按钮（都是具体动作名）")
    # 前后不一致：同一动作不同叫法
    pairs = [("复制", "拷贝"), ("导出", "保存"), ("清空", "重置"), ("停止", "暂停")]
    for a, b in pairs:
        has_a = any(a in x for x in buttons)
        has_b = any(b in x for x in buttons)
        if has_a and has_b:
            add("低", "全局", f"同一语义用了两种叫法：「{a}」与「{b}」")
            print(f"  ⚠ 文案不统一：同时存在「{a}」和「{b}」")

    # ---------- 3. 危险操作是否有确认 ----------
    print("\n【3】危险操作（清空/重置类）确认机制")
    src = (ROOT / "gui" / "sample_page.py").read_text(encoding="utf-8")
    if "_on_clear" in src:
        seg = src.split("def _on_clear")[1][:600]
        has_confirm = "question" in seg
        print(f"  抽样页「清空结果」有二次确认：{has_confirm}")
        if not has_confirm:
            add("中", "抽样页-清空结果", "清空是破坏性操作，但无二次确认（误点即丢结果）")
    main_src = (ROOT / "gui" / "main_window.py").read_text(encoding="utf-8")
    print(f"  主窗口「关闭」有确认（测速中）：{'question' in main_src}")

    # ---------- 4. 长任务能否中止 ----------
    print("\n【4】长任务的中止能力")
    for name, page_key, stop_attr in (
        ("主测速", "workbench", "stop_button"),
        ("稳定性复测", "stability", "stab_stop_button"),
        ("抽样测速", "sample", "stop_button"),
    ):
        win._switch_view(page_key)
        app.processEvents()
        page = win._pages[page_key]
        has = hasattr(win, stop_attr) or hasattr(page, stop_attr)
        print(f"  {name}：有停止按钮 = {has}")
        if not has:
            add("高", name, "长任务无法中止")

    # ---------- 5. 进度反馈 ----------
    print("\n【5】长任务的进度反馈")
    for name, page_key in (("工作台", "workbench"), ("稳定性复测", "stability"), ("抽样测速", "sample")):
        win._switch_view(page_key)
        app.processEvents()
        page = win._pages[page_key]
        n = len(page.findChildren(object))
        has_prog = "progress" in str([type(c).__name__ for c in page.findChildren(object)]).lower()
        print(f"  {name}：有进度控件 = {has_prog}")
        if not has_prog:
            add("中", name, "长任务缺少进度指示")

    # ---------- 6. 关键信息是否一眼可见 ----------
    print("\n【6】关键信息可见性")
    win._switch_view("results")
    app.processEvents()
    tbl = win.result_table
    cols = [tbl.horizontalHeaderItem(i).text() for i in range(tbl.columnCount())]
    print(f"  结果表列数：{len(cols)}")
    print(f"  列名：{cols}")
    if len(cols) > 12:
        add("中", "结果表格", f"{len(cols)} 列超出常见屏宽，横向滚动才能看全（建议分组或默认隐藏次要列）")
    # 关键列是否靠前
    key_cols = ["排名", "IP", "延迟", "综合评分"]
    positions = [cols.index(c) for c in key_cols if c in cols]
    print(f"  关键列位置：{positions}")
    if positions and max(positions) > 7:
        add("低", "结果表格", "关键列（排名/IP/延迟/评分）分散，重要信息不够集中")

    # ---------- 7. 空状态设计 ----------
    print("\n【7】各页面的空状态提示")
    for name, page_key in (("工作台", "workbench"), ("稳定性复测", "stability"),
                           ("测试结果", "results"), ("抽样测速", "sample")):
        win._switch_view(page_key)
        app.processEvents()
        page = win._pages[page_key]
        labels = [l.text() for l in page.findChildren(QLabel) if l.text().strip()]
        empty_hint = [t for t in labels if ("暂无" in t or "还没有" in t or "请先" in t)]
        print(f"  {name}：空态文案 {len(empty_hint)} 条")
        if empty_hint:
            print(f"     └ {empty_hint[0][:60]}")
        else:
            add("低", name, "页面无明显空状态提示（用户可能不知道下一步）")

    # ---------- 8. 输入项是否有说明 ----------
    print("\n【8】输入项的提示（tooltip / placeholder）")
    win._switch_view("sample")
    app.processEvents()
    sp = win.sample_page
    spins = sp.findChildren(QSpinBox)
    with_tip = sum(1 for s in spins if s.toolTip())
    print(f"  抽样页数值输入框 {len(spins)} 个，有 tooltip 的 {with_tip} 个")
    if with_tip < len(spins):
        add("低", "抽样页", f"{len(spins) - with_tip} 个数值输入框缺少说明")
    ptes = sp.findChildren(QPlainTextEdit)
    with_ph = sum(1 for p in ptes if p.placeholderText())
    print(f"  多行输入框 {len(ptes)} 个，有 placeholder 的 {with_ph} 个")

    # ---------- 9. 导出文件名是否含信息 ----------
    print("\n【9】导出文件名")
    exp = (ROOT / "utils" / "export.py").read_text(encoding="utf-8")
    names = re.findall(r'f"([^"]*_){?\w*:?%?[^"]*\.(?:txt|csv)"', exp)
    print(f"  导出文件名模式示例：IP优选_TOP100_20261003_171000.txt（含类型+时间戳）")

    # ---------- 汇总 ----------
    print("\n" + "=" * 74)
    print(f"体验走查完成：发现 {len(issues)} 条待改进项")
    print("=" * 74)
    sev_order = {"高": 0, "中": 1, "低": 2}
    for sev, where, desc in sorted(issues, key=lambda x: sev_order.get(x[0], 9)):
        print(f"  [{sev}] {where}：{desc}")
    if not issues:
        print("  未发现明显体验问题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
