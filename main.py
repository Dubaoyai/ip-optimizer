"""IP优化器 —— 程序入口。

运行方式（在项目根目录执行）：
    python main.py
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

from PySide6.QtWidgets import QApplication, QMessageBox

from gui import theme
from gui.main_window import APP_TITLE, MainWindow
from utils.logger import ensure_runtime_dirs, get_logger


def _install_exception_hook(logger) -> None:
    """把未捕获的异常写入日志，并用中文弹窗提示用户，避免程序无声崩溃。"""

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        # 用户按 Ctrl+C 时按默认方式处理
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.error("程序发生未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))
        try:
            QMessageBox.critical(
                None,
                "程序错误",
                f"程序发生错误：{exc_value}\n\n详细信息请查看 logs/app.log",
            )
        except Exception:
            pass  # 弹窗本身失败时忽略，避免二次异常

    sys.excepthook = handle_exception


def _apply_app_icon(app: QApplication, logger) -> None:
    """设置程序图标（任务栏 / 窗口 / Alt+Tab 共用）。

    图标文件 `assets/app.ico` 由中枢「图标工坊」skill 生成（矢量重绘，
    保证 16px 下的可辨识性）。

    路径解析要同时适配两种运行方式：
    - 源码运行：`main.py` 所在目录（项目根）下的 assets/；
    - PyInstaller 打包：资源被解包到临时目录，须从 `sys._MEIPASS` 取。

    ⚠️ 图标缺失**不应影响程序启动** —— 找不到就记一条日志跳过。

    Args:
        app: QApplication 实例。
        logger: 日志器。
    """
    try:
        from PySide6.QtGui import QIcon

        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        icon_path = base / "assets" / "app.ico"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
            logger.info("程序图标已加载：%s", icon_path)
        else:
            logger.info("未找到程序图标（%s），使用系统默认图标", icon_path)
    except Exception as exc:  # noqa: BLE001
        # 图标是纯观感项，失败不应阻断启动
        logger.warning("加载程序图标失败：%s", exc)


def main() -> int:
    """程序主函数。"""
    # 确保 logs、output 目录存在
    ensure_runtime_dirs()
    logger = get_logger()
    logger.info("-" * 50)
    logger.info("%s 启动", APP_TITLE)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_TITLE)
    _install_exception_hook(logger)

    # 程序图标：任务栏、窗口标题栏、Alt+Tab 都用它
    _apply_app_icon(app, logger)

    # 应用主题：**每次启动固定用深色**（产品要求）。
    # 早期版本会把用户上次的选择写盘并在下次启动沿用，导致
    # 「设了默认深色，打开却是浅色」。现在启动恒为深色，
    # 会话内仍可由右上角下拉框随时切换。
    theme.discard_legacy_preference(logger)
    startup_mode = theme.load_saved_mode()
    theme.apply_theme(app, startup_mode)
    logger.info("主题模式：%s（右上角可切换；启动恒为深色）", startup_mode)

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    logger.info("%s 退出（退出码 %s）", APP_TITLE, exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())