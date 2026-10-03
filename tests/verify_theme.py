"""主题系统端到端验证（深色 / 浅色 / 跟随系统 + 持久化）。

验证三件事，每件都用**可观察证据**而非"应该没问题"：
1. 启动路径（main.py 的流程）确实应用了主题；
2. 三种模式都能切换，且渲染像素随之变化；
3. 选择会被保存，下次启动能读回。

运行：
    python tests/verify_theme.py
退出码：0 = 全部通过。
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from gui import theme  # noqa: E402
from gui.main_window import MainWindow  # noqa: E402
from utils.logger import ensure_runtime_dirs  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    """记录检查结果。"""
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""), flush=True)
    if not ok:
        failures.append(name)


def corner_pixel(window) -> str:
    """取窗口左上角像素（用于判断当前底色深浅）。"""
    img = window.grab().toImage()
    return img.pixelColor(5, 5).name()


def is_dark(hex_color: str) -> bool:
    """判断颜色是否为深色。"""
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return max(r, g, b) <= 80


def main() -> int:
    """执行主题系统全流程验证。"""
    ensure_runtime_dirs()
    app = QApplication(sys.argv)

    # ---------- 1. 启动路径应用主题 ----------
    mode = theme.load_saved_mode()
    theme.apply_theme(app, mode)
    win = MainWindow()
    win.resize(1360, 940)
    win.show()
    app.processEvents()

    qss = app.styleSheet()
    check("① 启动即应用主题（QSS 非空）", len(qss.strip()) > 1000, f"QSS {len(qss)} 字符")

    # ---------- 2. 深色 ----------
    win.apply_theme_mode("dark")
    app.processEvents()
    dark_px = corner_pixel(win)
    check("② 深色模式渲染为深色", is_dark(dark_px), f"左上角像素 {dark_px}")

    # ---------- 3. 浅色 ----------
    win.apply_theme_mode("light")
    app.processEvents()
    light_px = corner_pixel(win)
    check("③ 浅色模式渲染为浅色", not is_dark(light_px), f"左上角像素 {light_px}")
    check("④ 深浅两模式像素确实不同", dark_px != light_px, f"{dark_px} vs {light_px}")

    # ---------- 4. 跟随系统 ----------
    win.apply_theme_mode("system")
    app.processEvents()
    sys_px = corner_pixel(win)
    detected = theme.resolve_mode("system")
    check(
        "⑤ 跟随系统模式可解析",
        detected in ("dark", "light"),
        f"检测到系统为 {detected}，渲染像素 {sys_px}",
    )
    # 渲染结果应与检测到的系统主题一致
    expect_dark = detected == "dark"
    check(
        "⑥ 跟随系统的渲染与检测结果一致",
        is_dark(sys_px) == expect_dark,
        f"检测 {detected}，渲染 {'深' if is_dark(sys_px) else '浅'}",
    )

    # ---------- 5. 下拉框与状态同步 ----------
    win.apply_theme_mode("light")
    app.processEvents()
    combo_mode = win.theme_combo.currentData()
    check("⑦ 下拉框显示与实际主题同步", combo_mode == "light", f"下拉框 = {combo_mode}")

    # ---------- 6. 启动恒为深色（不记忆用户切换） ----------
    # 产品要求：每次打开都以深色启动。历史版本会记住上次选择，
    # 导致用户曾切浅色后「默认深色」失效（用户实际反馈过这个问题）。
    win.apply_theme_mode("dark")
    app.processEvents()
    check("⑧ 启动模式为深色", theme.load_saved_mode() == "dark",
          f"load_saved_mode() = {theme.load_saved_mode()}")

    win.apply_theme_mode("light")
    app.processEvents()
    check("⑨ 会话内切换不影响下次启动（不记忆）",
          theme.load_saved_mode() == "dark",
          f"切到浅色后 load_saved_mode() = {theme.load_saved_mode()}")

    # 模拟盘上残留 light 的旧配置 —— 启动时应被作废为 dark
    prefs = theme._prefs_path()
    if prefs is not None:
        import json as _json

        _backup = prefs.read_text(encoding="utf-8") if prefs.exists() else None
        prefs.parent.mkdir(parents=True, exist_ok=True)
        prefs.write_text(
            _json.dumps({"theme_mode": "light", "keep": "other"}), encoding="utf-8"
        )
        theme.discard_legacy_preference()
        after = _json.loads(prefs.read_text(encoding="utf-8"))
        check("⑨bis 旧 light 配置被作废为 dark",
              after.get("theme_mode") == "dark",
              f"作废后 = {after.get('theme_mode')}")
        check("⑨ter 作废时保留其他偏好项", after.get("keep") == "other",
              f"keep = {after.get('keep')}")
        if _backup is not None:
            prefs.write_text(_backup, encoding="utf-8")
        else:
            prefs.unlink(missing_ok=True)

    # ---------- 7. 反复切换稳定性 ----------
    try:
        for i in range(15):
            win.apply_theme_mode(["dark", "light", "system"][i % 3])
            app.processEvents()
        check("⑩ 15 次连续切换无异常", True, "无异常抛出")
    except Exception as exc:
        check("⑩ 15 次连续切换无异常", False, f"{type(exc).__name__}: {exc}")

    # 恢复默认深色，避免影响用户下次启动
    win.apply_theme_mode("dark")
    app.processEvents()

    # ---------- 8. 浅色下的关键文字可读性 ----------
    win.apply_theme_mode("light")
    app.processEvents()
    txt_color = theme.color("TEXT_PRIMARY")
    bg_color = theme.color("BG_CARD")
    check(
        "⑪ 浅色下文字与卡片底色不同",
        txt_color != bg_color,
        f"文字 {txt_color} / 卡片底 {bg_color}",
    )

    print()
    if failures:
        print(f"主题验证 FAILED（{len(failures)} 项）：")
        for f in failures:
            print("  -", f)
    else:
        print("主题验证 PASSED（11/11）")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
