"""结果页截图（含新增的代理模板与节点按钮）。"""

from __future__ import annotations

import os
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="ipo_shot_"))
os.environ["IPO_SAMPLE_PREFS"] = str(_TMP / "p.json")
os.environ["IPO_SAMPLE_RESULTS"] = str(_TMP / "r.json")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.ranking import build_ranking  # noqa: E402
from core.tcp_tester import TestResult  # noqa: E402
from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402


def mk(ip: str, latency: int, port: int = 443) -> TestResult:
    """构造成功结果。"""
    base = TestResult(ip=ip, port=port, latency=latency, success=True, error=None)
    return replace(
        base, http_tested=True, http_status=200, http_latency=latency,
        download_tested=True, download_speed_bps=5_200_000.0, download_error=None,
    )


def main() -> int:
    """截图。"""
    ensure_runtime_dirs()
    out = ROOT / "output" / "ui_shots"
    out.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    theme.apply_theme(app, "dark")
    win = MainWindow()
    win.resize(1440, 960)
    win.show()

    fake = [mk("104.16.0.1", 50), mk("104.16.0.2", 90, 80), mk("172.64.1.8", 130),
            mk("104.24.2.5", 180), mk("162.158.3.9", 240, 80)]
    win._all_results = fake
    # 走正常刷新链路（而非直接 set_ranking），确保空态/按钮状态与真实使用一致
    win._refresh_ranking_view()
    win.result_template_edit.setText(
        "vless://11111111-2222-3333-4444-555555555555@1.2.3.4:443"
        "?encryption=none&security=none&type=ws&host=my-own.workers.dev#优选节点"
    )
    win._switch_view("results")

    def shoot() -> None:
        app.processEvents()
        for mode in ("dark", "light"):
            theme.apply_theme(app, mode)
            app.processEvents()
            path = out / f"result-nodes-{mode}.png"
            win.grab().save(str(path))
            print(f"OK {path}", flush=True)
        theme.apply_theme(app, "dark")
        app.quit()

    QTimer.singleShot(700, shoot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
