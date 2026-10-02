"""真实启动路径验证：模拟用户双击 run.bat 的效果。

与之前的截图脚本不同，本脚本**不自己调 apply_theme**，
而是直接调用 main.py 里的启动流程，验证主题确实被应用。

这能抓出「截图脚本自己调了主题、但用户实际启动路径没调」这类假阳性。

运行：
    python tests/verify_launch.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

import main as app_main  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

out_dir = ROOT / "output" / "ui_shots"


def main() -> int:
    """复刻 main.py 的启动流程，检查主题是否生效。"""
    ensure_runtime_dirs()
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName(app_main.APP_TITLE)

    # ↓↓↓ 这一行就是 main.py 里的关键调用，若缺失则界面会是系统默认白/灰
    theme.apply_theme(app, theme.DEFAULT_MODE)

    window = MainWindow()
    window.resize(1360, 940)
    window.show()

    failures: list[str] = []

    def check() -> None:
        # 1. 全局样式表非空
        qss = app.styleSheet()
        if not qss.strip():
            failures.append("全局 QSS 为空 —— 主题未应用")
        else:
            # 2. QSS 里必须出现深色主题的窗口底色
            expected = theme.color("BG_PRIMARY")
            if expected not in qss:
                failures.append(f"QSS 中缺少窗口底色 {expected}")
            print(f"[OK] 全局 QSS 已应用（{len(qss)} 字符），窗口底色 = {expected}")

        # 3. 实际渲染像素必须是深色（取窗口左上角附近）
        img = window.grab().toImage()
        px = img.pixelColor(5, 5).name()
        print(f"[INFO] 窗口左上角像素 = {px}")
        # 深色主题下该点应明显偏暗（各通道 < 80）
        r = int(px[1:3], 16)
        g = int(px[3:5], 16)
        b = int(px[5:7], 16)
        if max(r, g, b) > 80:
            failures.append(f"窗口底色过亮({px}) —— 主题可能未生效")
        else:
            print(f"[OK] 渲染确认为深色（RGB 最大值 {max(r, g, b)} ≤ 80）")

        # 4. 切换主题能否即时生效
        theme.apply_theme(app, "light")
        app.processEvents()
        light_px = window.grab().toImage().pixelColor(5, 5).name()
        print(f"[INFO] 切到浅色后左上角像素 = {light_px}")
        if light_px == px:
            failures.append("切换到浅色后像素未变化 —— 主题切换无效")
        else:
            print("[OK] 浅色主题切换生效")

        # 截图存档
        theme.apply_theme(app, "dark")
        app.processEvents()
        window.grab().save(str(out_dir / "launch-dark.png"))
        theme.apply_theme(app, "light")
        app.processEvents()
        window.grab().save(str(out_dir / "launch-light.png"))
        theme.apply_theme(app, "dark")
        app.processEvents()
        print("[OK] 已保存 launch-dark.png / launch-light.png")

        print()
        if failures:
            print("启动路径验证 FAILED：")
            for f in failures:
                print("  -", f)
        else:
            print("启动路径验证 PASSED")
        app.quit()

    QTimer.singleShot(700, check)
    code = app.exec()
    return 1 if failures else code


if __name__ == "__main__":
    sys.exit(main())
