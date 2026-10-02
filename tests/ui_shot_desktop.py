"""真实桌面环境下的界面截图（用于核对字体与最终观感）。

与 ui_smoke_shot.py 的区别：本脚本**不**使用 offscreen 平台，
而是在真实 Windows 桌面会话中渲染后截图，因此字体渲染与用户所见一致。

运行：
    python tests/ui_shot_desktop.py
产物：
    output/ui_shots/desktop-*.png
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402


def main() -> int:
    """在真实平台下截图三个视图。"""
    ensure_runtime_dirs()
    out_dir = ROOT / "output" / "ui_shots"
    out_dir.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    theme.apply_theme(app)

    window = MainWindow()
    window.resize(1360, 940)
    window.show()

    def grab_all() -> None:
        for key in ("workbench", "results", "stability"):
            window._switch_view(key)
            app.processEvents()
            path = out_dir / f"desktop-{key}.png"
            ok = window.grab().save(str(path))
            print(f"{'OK ' if ok else 'FAIL'} {path}", flush=True)
        print("完成", flush=True)
        app.quit()

    QTimer.singleShot(900, grab_all)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
