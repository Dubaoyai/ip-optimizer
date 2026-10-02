"""抽样测速页面截图（用于人工核对排版）。

运行：
    python tests/shot_sample_page.py
产物：
    output/ui_shots/sample-{dark,light}.png
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.sampler import ProbeResult  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402


def main() -> int:
    """截取抽样页面在深浅两种主题下的样子。"""
    ensure_runtime_dirs()
    out = ROOT / "output" / "ui_shots"
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")
    win = MainWindow()
    win.resize(1440, 960)
    win.show()

    page = win.sample_page
    win._switch_view("sample")
    # 塞几条结果，让截图能看出表格与统计的真实样子
    page._engine.passing = [
        ProbeResult(ip="104.16.0.12", port=443, ms=42.0,
                    node="vless://fa40af57-9498-46db-b347-975d38f306a5@104.16.0.12:443?encryption=none&security=none&type=ws"),
        ProbeResult(ip="172.64.1.8", port=80, ms=98.0,
                    node="vless://fa40af57-9498-46db-b347-975d38f306a5@172.64.1.8:80?encryption=none&security=none&type=ws"),
        ProbeResult(ip="104.24.3.77", port=443, ms=210.0,
                    node="vless://fa40af57-9498-46db-b347-975d38f306a5@104.24.3.77:443?encryption=none&security=none&type=ws"),
    ]
    page._engine.tested = {r.node for r in page._engine.passing}
    page._render_table()
    page._update_stats()

    def shoot() -> None:
        app.processEvents()
        for mode in ("dark", "light"):
            theme.apply_theme(app, mode)
            app.processEvents()
            path = out / f"sample-{mode}.png"
            win.grab().save(str(path))
            print(f"OK {path}", flush=True)
        theme.apply_theme(app, "dark")
        app.quit()

    QTimer.singleShot(700, shoot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
