"""Application entry point."""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import config
from .runtime import AppContext
from .ui.main_window import MainWindow
from .ui.theme import apply_theme


def run():
    app = QApplication(sys.argv)
    app.setApplicationName(config.APP_NAME)
    app.setWindowIcon(QIcon(str(config.ASSETS / "logo-mark.png")))
    ctx = AppContext()
    app.setStyleSheet(apply_theme(ctx.db.kv_get("theme", "Midnight")))
    app.aboutToQuit.connect(ctx.db.close)
    ctx.shutdown_requested.connect(app.quit)
    win = MainWindow(ctx)
    win.showFullScreen()
    profile = ctx.db.profile()
    if not profile["setup_complete"] or not profile.get("password_hash"):
        win.run_wizard()
    QTimer.singleShot(500, ctx.ensure_ai_ready)
    return app.exec()
