from datetime import datetime

from PySide6.QtCore import QEasingCurve, Qt, QPropertyAnimation, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMainWindow, QScrollArea, QStackedWidget,
    QToolButton, QVBoxLayout, QWidget,
)

from .. import config
from .lock_screen import LockScreen
from .pages import PAGES
from .pages.wizard import SetupWizard
from .widgets import DotGrid, button, dock_icon, label


class MainWindow(QMainWindow):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.buttons = {}
        self.pages, self.holders, self.effects = {}, {}, {}
        self._locked = False
        self._animation = None
        self.setWindowTitle("StudiOS")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(900, 600)

        self.shell_stack = QStackedWidget()
        self.setCentralWidget(self.shell_stack)
        self.desktop = QWidget()
        self.desktop.setObjectName("desktop")
        self.desktop.setStyleSheet("#desktop{background:#0b0d18;}")
        self.shell_stack.addWidget(self.desktop)
        self.lock_screen = LockScreen(ctx)
        self.shell_stack.addWidget(self.lock_screen)
        self.lock_screen.unlocked.connect(self.unlock)

        root = QVBoxLayout(self.desktop)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self._build_topbar(root)

        self.field = DotGrid()
        fl = QVBoxLayout(self.field)
        fl.setContentsMargins(28, 20, 28, 16)
        self.stack = QStackedWidget()
        fl.addWidget(self.stack)
        root.addWidget(self.field, 1)
        self._build_dock(root)

        self.toast_lbl = QLabel(self.field)
        self.toast_lbl.setStyleSheet(
            "background:#1a1e35;border:1px solid #343a5e;border-left:3px solid #7c8cff;"
            "border-radius:8px;padding:9px 14px;")
        self.toast_lbl.hide()
        self.toast_timer = QTimer(self, singleShot=True, interval=3500)
        self.toast_timer.timeout.connect(self.toast_lbl.hide)

        ctx.navigate.connect(self.go)
        ctx.status_changed.connect(self.on_status)
        ctx.ai_setup_changed.connect(self.on_ai_setup)
        ctx.data_changed.connect(self.on_data)
        ctx.toast.connect(self.show_toast)

        self.build_dock()
        self.on_data("profile")
        self.tick()
        self.clock_timer = QTimer(self, interval=1000)
        self.clock_timer.timeout.connect(self.tick)
        self.clock_timer.start()
        self.go("dashboard")
        self.lock()

    def _build_topbar(self, root):
        top = QWidget()
        top.setObjectName("topBar")
        top.setFixedHeight(64)
        top.setStyleSheet("#topBar{background:#101326;border-bottom:1px solid #262b47;}")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(24, 0, 20, 0)
        tl.setSpacing(12)
        mark = QLabel()
        mark.setPixmap(QPixmap(str(config.ASSETS / "logo-mark.png")).scaled(
            34, 34, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        tl.addWidget(mark)
        self.greeting = label("", "h2")
        tl.addWidget(self.greeting)
        tl.addStretch(1)
        self.ai_indicator = label("●  AI dormant", muted=True)
        self.ai_indicator.setObjectName("aiIndicator")
        tl.addWidget(self.ai_indicator)
        tl.addStretch(1)
        self.clock = label("", "mono", muted=True)
        tl.addWidget(self.clock)
        self.avatar = label("S")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(34, 34)
        self.avatar.setStyleSheet("background:#252b50;color:#aab2ff;border-radius:17px;font-weight:600;")
        tl.addWidget(self.avatar)
        logout = self._control("Log out")
        logout.setToolTip("Lock your StudiOS session")
        logout.clicked.connect(self.lock)
        tl.addWidget(logout)
        minimize = self._control("—")
        minimize.setToolTip("Minimize")
        minimize.clicked.connect(self.showMinimized)
        tl.addWidget(minimize)
        close = self._control("×")
        close.setToolTip("Close StudiOS")
        close.clicked.connect(self.close)
        tl.addWidget(close)
        root.addWidget(top)

    @staticmethod
    def _control(text):
        b = QToolButton()
        b.setText(text)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(38, 34)
        b.setStyleSheet(
            "QToolButton{background:transparent;border:0;border-radius:8px;color:#a7abc2;font-size:15px;}"
            "QToolButton:hover{background:#252b46;color:#ffffff;}")
        return b

    def _build_dock(self, root):
        dock = QWidget()
        dock.setObjectName("dockBar")
        dock.setFixedHeight(92)
        dock.setStyleSheet("#dockBar{background:#101326;border-top:1px solid #262b47;}")
        self.nav_box = QHBoxLayout(dock)
        self.nav_box.setContentsMargins(18, 8, 18, 8)
        self.nav_box.setSpacing(6)
        self.nav_box.addStretch(1)
        root.addWidget(dock)

    def _dock_button(self, pid):
        b = QToolButton()
        b.setObjectName("dock")
        b.setText(PAGES[pid][0])
        b.setIcon(dock_icon(pid))
        b.setIconSize(b.iconSize() * 1.25)
        b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        b.setCheckable(True)
        b.setAutoExclusive(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFixedSize(70, 72)
        b.clicked.connect(lambda _=False, page=pid: self.go(page))
        self.buttons[pid] = b
        return b

    def build_dock(self):
        while self.nav_box.count():
            item = self.nav_box.takeAt(0)
            if item is not None:
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
        self.nav_box.addStretch(1)
        for pid in PAGES:
            self.nav_box.addWidget(self.buttons.get(pid) or self._dock_button(pid))
        self.nav_box.addStretch(1)

    def go(self, pid):
        if self._locked or pid not in PAGES:
            return
        if pid not in self.pages:
            page = PAGES[pid][1](self.ctx)
            self.pages[pid] = page
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            if page.scroll:
                sc = QScrollArea()
                sc.setWidgetResizable(True)
                sc.setFrameShape(QFrame.Shape.NoFrame)
                sc.viewport().setAutoFillBackground(False)
                sc.setWidget(page)
                hl.addWidget(sc)
            else:
                hl.addWidget(page)
            effect = QGraphicsOpacityEffect(holder)
            effect.setOpacity(1)
            holder.setGraphicsEffect(effect)
            self.stack.addWidget(holder)
            self.holders[pid] = holder
            self.effects[pid] = effect
        self.stack.setCurrentWidget(self.holders[pid])
        self.pages[pid].on_show()
        if pid in self.buttons:
            self.buttons[pid].setChecked(True)
        if pid in ("assistant", "revision"):
            self.ctx.ensure_ai_status()
        effect = self.effects[pid]
        effect.setOpacity(0.82)
        self._animation = QPropertyAnimation(effect, b"opacity", self)
        self._animation.setDuration(150)
        self._animation.setStartValue(0.82)
        self._animation.setEndValue(1.0)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.start()

    def lock(self):
        self._locked = True
        self.lock_screen.refresh()
        self.shell_stack.setCurrentWidget(self.lock_screen)

    def unlock(self):
        self._locked = False
        self.shell_stack.setCurrentWidget(self.desktop)

    def on_status(self, status):
        if not status.get("running"):
            text, color = "●  AI offline", "#ff6b7a"
        elif status.get("model_ready"):
            text, color = f"●  {status['active']} ready", "#5fd3a0"
        else:
            text, color = f"●  Install {status.get('preferred', config.DEFAULT_OLLAMA['model'])}", "#f2b75c"
        self.ai_indicator.setText(text)
        self.ai_indicator.setStyleSheet(f"color:{color};")
        assistant = self.pages.get("assistant")
        if assistant:
            assistant.update_status(status)
        settings = self.pages.get("settings")
        if settings:
            settings.show_status(status)

    def on_ai_setup(self, state):
        terminal = self.pages.get("terminal")
        if terminal:
            terminal.show_state(state)
        settings = self.pages.get("settings")
        if settings:
            settings._setup_update(state)
        phase = state.get("phase")
        prompt = getattr(self, "setup_prompt", None)
        if phase == "ready" and prompt:
            prompt.close()
            return
        if phase not in ("downloading", "error"):
            return
        message = state.get("message")
        if not message:
            message = state.get("status", "Downloading the configured model…")
            if state.get("percent") is not None:
                message += f" · {state['percent']}%"
        if prompt:
            self.setup_prompt_message.setText(message)
            self.setup_retry_button.setVisible(phase == "error")
            return
        dialog = QDialog(self, Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        dialog.setObjectName("aiSetupPrompt")
        dialog.setStyleSheet(
            "#aiSetupPrompt{background:#151a30;border:1px solid #414a78;border-radius:16px;}")
        dialog.setWindowTitle("Local AI setup")
        dialog.setModal(False)
        dialog.setMinimumWidth(440)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(26, 22, 26, 22)
        layout.addWidget(label(
            "Setting up local AI" if phase == "downloading" else "Local AI needs attention", "h2"))
        self.setup_prompt_message = label(message, muted=True, wrap=True)
        layout.addWidget(self.setup_prompt_message)
        actions = QHBoxLayout()
        self.setup_retry_button = button("Retry setup", "primary", self._retry_ai_setup)
        self.setup_retry_button.setVisible(phase == "error")
        dismiss = button("Continue to lock screen", "ghost", dialog.close)
        actions.addWidget(self.setup_retry_button)
        actions.addStretch(1)
        actions.addWidget(dismiss)
        layout.addLayout(actions)
        self.setup_prompt = dialog
        dialog.finished.connect(lambda: setattr(self, "setup_prompt", None))
        dialog.show()

    def _retry_ai_setup(self):
        prompt = getattr(self, "setup_prompt", None)
        if prompt:
            prompt.close()
        self.ctx.ensure_ai_ready(force=True)

    def on_data(self, what):
        if what == "profile":
            profile = self.ctx.db.profile()
            name = profile.get("name") or "there"
            hour = datetime.now().hour
            greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
            self.greeting.setText(f"{greeting}, {name}")
            self.avatar.setText(name[:1].upper())
            self.build_dock()
        elif what == "theme":
            for pid, button in self.buttons.items():
                button.setIcon(dock_icon(pid))

    def tick(self):
        self.clock.setText(datetime.now().strftime("%a %d %b  ·  %H:%M"))

    def show_toast(self, text):
        self.toast_lbl.setText(text)
        self.toast_lbl.adjustSize()
        self.toast_lbl.move(self.field.width() - self.toast_lbl.width() - 24,
                            self.field.height() - self.toast_lbl.height() - 20)
        self.toast_lbl.show()
        self.toast_lbl.raise_()
        self.toast_timer.start()

    def run_wizard(self):
        SetupWizard(self.ctx, self).exec()
        self.on_data("profile")
        self.lock_screen.refresh()
        for page in self.pages.values():
            page.refresh()
