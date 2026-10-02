"""界面冒烟测试 + 截图。

用途：在不人工点击的前提下，确认主窗口能正常构建、黑灰主题生效，
并把三个视图各截一张图，供人工核对排版。

运行：
    python tests/ui_smoke_shot.py
产物：
    output/ui_shots/*.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 允许从项目根目录直接运行
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402


def main() -> int:
    """构建主窗口并把三个视图分别截图。"""
    ensure_runtime_dirs()
    out_dir = ROOT / "output" / "ui_shots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    theme.apply_theme(app)

    window = MainWindow()
    window.resize(1280, 900)
    window.show()

    def grab_all() -> None:
        """依次切换视图并截图。"""
        views = ("workbench", "results", "stability")
        for key in views:
            window._switch_view(key)
            app.processEvents()
            pixmap = window.grab()
            target = out_dir / f"view-{key}.png"
            ok = pixmap.save(str(target))
            print(f"{'OK ' if ok else 'FAIL'} {target} ({pixmap.width()}x{pixmap.height()})", flush=True)

        # 顺带验证对话框能构建
        from gui.fetch_dialog import FetchSettingsDialog

        dlg = FetchSettingsDialog(window)
        dlg.show()
        app.processEvents()
        dlg_path = out_dir / "dialog-fetch.png"
        ok = dlg.grab().save(str(dlg_path))
        print(f"{'OK ' if ok else 'FAIL'} {dlg_path}", flush=True)
        dlg.close()

        print("界面冒烟测试完成", flush=True)
        app.quit()

    QTimer.singleShot(600, grab_all)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
