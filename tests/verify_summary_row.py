"""验证「端口分布」显示为单行、与相邻标签水平对齐。

真实场景：端口分布文字较长时（如「端口分布: 80×103  443×47」），
旧实现会折行导致与左侧指标上下错位。

运行：
    python tests/verify_summary_row.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 重定向配置，避免污染用户文件
_TMP = Path(tempfile.mkdtemp(prefix="ipo_summary_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "p.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "r.json")

from PySide6.QtWidgets import QApplication  # noqa: E402

import core.sampler as sampler_mod  # noqa: E402
from core.sampler import SampleStats  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录一项检查。"""
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)


def main() -> int:
    """验证汇总行的单行显示与对齐。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")
    win = MainWindow()
    win.resize(1440, 960)
    win.show()
    win._switch_view("sample")
    app.processEvents()
    page = win.sample_page

    # 伪造一个「端口很多」的统计，模拟用户截图里的场景
    fake = SampleStats(
        passing=150,
        fastest_ms=42.0,
        avg_ms=117.0,
        success_rate=76.5,
        port_dist=[(80, 103), (443, 47), (8443, 12), (2052, 5), (2082, 3)],
    )
    original = sampler_mod.summarize
    sampler_mod.summarize = lambda *_a, **_k: fake
    # 页面内部通过模块引用调用，需同步替换页面命名空间里的引用
    import gui.sample_page as page_mod

    page_mod.summarize = lambda *_a, **_k: fake
    try:
        page._update_stats()
        app.processEvents()
    finally:
        sampler_mod.summarize = original

    text = page.port_label.text()
    print(f"\n端口分布显示：{text!r}\n")

    # 1. 不换行
    check("端口分布标签禁用换行", not page.port_label.wordWrap())
    check("存活率标签禁用换行", not page.rate_label.wordWrap())
    check("平均延迟标签禁用换行", not page.avg_label.wordWrap())

    # 2. 三标签等高（等高 ⇒ 同一行，无错位）
    h1, h2, h3 = page.rate_label.height(), page.avg_label.height(), page.port_label.height()
    check("三个标签等高（水平对齐）", h1 == h2 == h3, f"{h1}/{h2}/{h3}")

    # 3. 端口分布只显示 3 个 + 折叠计数
    check("端口分布最多列 3 个端口", text.count("×") <= 3, f"{text.count('×')} 个")
    check("多余端口折叠为 +N 提示", "+2种" in text, text)

    # 4. 完整分布进 tooltip（信息不丢）
    tip = page.port_label.toolTip()
    check("tooltip 含完整分布（5 个端口）", tip.count("×") == 5, tip)

    # 5. 标签确实在同一水平线（y 坐标一致）
    y1, y2, y3 = page.rate_label.y(), page.avg_label.y(), page.port_label.y()
    check("三个标签 y 坐标一致", y1 == y2 == y3, f"{y1}/{y2}/{y3}")

    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    print(f"汇总行验证：{passed}/{total} 通过")
    if passed < total:
        print("失败项：")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
