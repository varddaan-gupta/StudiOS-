from datetime import datetime

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QFrame, QLineEdit, QVBoxLayout, QWidget

from ..core.auth import verify_password
from .widgets import button, label


class LockScreen(QWidget):
    unlocked = Signal()

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.setObjectName("lockScreen")
        self.setStyleSheet(
            "#lockScreen{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #090b17,stop:.55 #151936,stop:1 #0b1020);}"
            "#lockCard{background:#151a30;border:1px solid #343a5e;border-radius:20px;}"
        )
        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.clock = label("", "statValue")
        self.clock.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.day = label("", muted=True)
        self.day.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card = QFrame()
        card.setObjectName("lockCard")
        card.setFixedWidth(390)
        form = QVBoxLayout(card)
        form.setContentsMargins(34, 30, 34, 30)
        form.setSpacing(14)
        self.avatar = label("S")
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setFixedSize(72, 72)
        self.avatar.setStyleSheet("background:#252b50;color:#aab2ff;border-radius:36px;font-size:30px;font-weight:600;")
        self.name = label("", "h2")
        self.name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.password = QLineEdit()
        self.password.setPlaceholderText("Enter your local password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.returnPressed.connect(self.unlock)
        self.message = label("Your study workspace is locked.", muted=True, wrap=True)
        self.message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unlock_button = button("Unlock StudiOS", "primary", self.unlock)
        for widget in (self.avatar, self.name, self.password, self.message, self.unlock_button):
            form.addWidget(widget, 0, Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(self.clock)
        outer.addWidget(self.day)
        outer.addSpacing(28)
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignCenter)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)
        self.refresh()
        self.tick()

    def refresh(self):
        profile = self.ctx.db.profile()
        name = profile.get("name") or "Student"
        self.name.setText(name)
        self.avatar.setText(name[:1].upper())
        self.password.clear()
        self.message.setText("Your study workspace is locked.")

    def tick(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%H:%M"))
        self.day.setText(now.strftime("%A, %d %B %Y"))

    def unlock(self):
        profile = self.ctx.db.profile()
        if verify_password(self.password.text(), profile.get("password_salt", ""),
                           profile.get("password_hash", "")):
            self.password.clear()
            self.unlocked.emit()
            return
        self.password.clear()
        self.message.setText("That password did not match. Try again.")
        self.password.setFocus()
