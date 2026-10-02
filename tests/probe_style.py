"""样式生效性探针：验证 #Card / #StatCard 的边框是否真的被 Qt 应用。

不靠肉眼看截图，直接读控件属性与样式表，给出可判定的结论。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme, widgets  # noqa: E402


def main() -> int:
    app = QApplication(sys.argv)
    theme.apply_theme(app)

    # 造一个 Panel 和一个 StatCard
    panel = widgets.Panel("测试面板", "副标题")
    card = widgets.StatCard("测试指标", "42", "个", "★")
    panel.show()
    card.show()
    app.processEvents()

    print("=== objectName 检查 ===")
    print(f"Panel.objectName      = {panel.objectName()!r}")
    print(f"StatCard.objectName   = {card.objectName()!r}")

    print("\n=== 全局 QSS 是否包含对应选择器 ===")
    qss = app.styleSheet()
    for sel in ("QWidget#Card", "QWidget#StatCard", "QFrame#PanelDivider"):
        print(f"{sel:24} -> {'命中' if sel in qss else '缺失'}")

    print("\n=== 实际渲染：把 Panel 渲染成图片并统计边框像素 ===")
    panel.resize(400, 200)
    app.processEvents()
    img = panel.grab().toImage()
    # 取上边缘第 1 行中央的像素，看是不是边框色 #282828
    mid_x = img.width() // 2
    top_px = img.pixelColor(mid_x, 0).name()
    inside_px = img.pixelColor(mid_x, 20).name()
    print(f"上边缘像素 = {top_px}  (期望边框色 {theme.BORDER})")
    print(f"内部像素   = {inside_px}  (期望卡片底 {theme.BG_CARD})")

    ok = top_px.lower() == theme.BORDER.lower()
    print(f"\n结论：面板边框 {'已生效' if ok else '未生效'}")

    # StatCard 同样检查
    card.resize(240, 92)
    app.processEvents()
    cimg = card.grab().toImage()
    c_top = cimg.pixelColor(cimg.width() // 2, 0).name()
    c_in = cimg.pixelColor(cimg.width() // 2, cimg.height() // 2).name()
    print(f"\n统计卡上边缘 = {c_top}  (期望 {theme.BORDER})")
    print(f"统计卡内部   = {c_in}  (期望 {theme.BG_CARD})")
    print(f"结论：统计卡边框 {'已生效' if c_top.lower() == theme.BORDER.lower() else '未生效'}")

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
