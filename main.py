"""数码解码 IP 优选器 V1.4 —— 程序入口。

运行方式（在项目根目录执行）：
    python main.py
"""

from __future__ import annotations

import sys
import types

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