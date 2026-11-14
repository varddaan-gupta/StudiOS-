import json

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDateEdit, QFileDialog, QGridLayout, QHBoxLayout, QLineEdit,
    QListWidget, QProgressBar, QVBoxLayout,
)

from ... import config
from ..theme import THEMES, apply_theme
from ..widgets import Panel, button, confirm, field, label, page_head
from .base import DynamicPage


class SettingsPage(DynamicPage):
    def build(self, layout):
        p, o = self.db.profile(), self.db.ollama_cfg()
        layout.addWidget(page_head("Settings", "Profile, workspace modules, the local AI engine and your data."))

        appearance = Panel("Appearance")
        self.theme = QComboBox()
        self.theme.addItems(list(THEMES))
        self.theme.setCurrentText(self.db.kv_get("theme", "Midnight"))
        appearance.body.addWidget(field("Accent theme", self.theme))
        appearance.body.addWidget(button("Apply theme", None, self.save_theme), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(appearance)

        # profile
        prof = Panel("Profile")
        self.name = QLineEdit(p["name"])
        self.exam = QComboBox()
        self.exam.setEditable(True)
        self.exam.addItems(config.EXAMS)
        self.exam.setCurrentText(p["exam"])
        self.exam_date = QDateEdit()
        self.exam_date.setCalendarPopup(True)
        self.has_date = QCheckBox("Exam date")
        try:
            y, m, d = map(int, p["exam_date"].split("-"))
            self.exam_date.setDate(QDate(y, m, d))
            self.has_date.setChecked(True)
        except ValueError:
            self.exam_date.setDate(QDate.currentDate())
        self.exam_date.setEnabled(self.has_date.isChecked())
        self.has_date.toggled.connect(self.exam_date.setEnabled)
        row = QHBoxLayout()
        row.addWidget(field("Name", self.name), 1)
        row.addWidget(field("Target exam or class", self.exam), 1)
        dbox = QVBoxLayout()
        dbox.addWidget(self.has_date)
        dbox.addWidget(self.exam_date)
        row.addLayout(dbox)
        prof.body.addLayout(row)
        prof.body.addWidget(label("Modules on your dashboard", muted=True))
        self.mods = {}
        mgrid = QGridLayout()
        module_options = [(mid, text) for mid, text in config.MODULES[1:]
                          if mid not in ("browser", "terminal")]
        for i, (mid, mlabel) in enumerate(module_options):
            cb = QCheckBox(mlabel)
            cb.setChecked(mid in p["modules"])
            self.mods[mid] = cb
            mgrid.addWidget(cb, i // 5, i % 5)
        prof.body.addLayout(mgrid)
        prof.body.addWidget(button("Save profile", "primary", self.save_profile), 0, Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(prof)

        # AI engine
        ai = Panel("AI engine (Ollama)")
        self.host = QLineEdit(o["host"])
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItem(o["model"])
        self.model.setCurrentText(o["model"])
        row = QHBoxLayout()
        row.addWidget(field("Ollama address", self.host), 1)
        row.addWidget(field("Model", self.model), 1)
        ai.body.addLayout(row)
        self.ai_status = label("", wrap=True)
        ai.body.addWidget(self.ai_status)
        ai.body.addWidget(label(f"Default lightweight model: {config.DEFAULT_OLLAMA['model']} (~1.5 GB).",
                                muted=True, wrap=True))
        self.installed = QListWidget()
        self.installed.setMaximumHeight(110)
        self.installed.itemClicked.connect(
            lambda it: self.model.setCurrentText(it.data(Qt.ItemDataRole.UserRole)))
        ai.body.addWidget(self.installed)
        self.pull_bar = QProgressBar()
        self.pull_bar.hide()
        self.pull_text = label("", muted=True)
        ai.body.addWidget(self.pull_bar)
        ai.body.addWidget(self.pull_text)
        btns = QHBoxLayout()
        btns.addWidget(button("Save and test connection", "primary", self.save_ai))
        self.pull_btn = button("Download this model", None, self.pull)
        btns.addWidget(self.pull_btn)
        btns.addStretch(1)
        ai.body.addLayout(btns)
        ai.body.addWidget(label(
            "StudiOS automatically starts the local Ollama service and downloads the configured model. "
            "If the runtime is missing, open System Setup for the official installer link.",
            muted=True, wrap=True))
        layout.addWidget(ai)

        # data
        data = Panel("Your data")
        data.body.addWidget(label(f"Stored on this computer in {config.DATA_DIR}. Nothing leaves it.", muted=True, wrap=True))
        row = QHBoxLayout()
        row.addWidget(button("Export backup", None, self.export))
        row.addWidget(button("Import backup", None, self.import_))
        row.addStretch(1)
        row.addWidget(button("Reset everything", "danger", self.reset))
        data.body.addLayout(row)
        layout.addWidget(data)
        self.show_status(self.ctx.status)

    # ---- profile ----
    def save_profile(self):
        self.db.set_profile(
            name=self.name.text().strip(), exam=self.exam.currentText().strip(),
            exam_date=self.exam_date.date().toString("yyyy-MM-dd") if self.has_date.isChecked() else "",
            modules=["dashboard", *[m for m, cb in self.mods.items() if cb.isChecked()]])
        self.ctx.data_changed.emit("profile")
        self.ctx.toast.emit("Profile saved")

    def save_theme(self):
        name = self.theme.currentText()
        stylesheet = apply_theme(name)
        self.db.kv_set("theme", name)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.setStyleSheet(stylesheet)
        self.ctx.data_changed.emit("theme")
        self.ctx.toast.emit(f"{name} theme applied")

    # ---- AI ----
    def show_status(self, s):
        self.installed.clear()
        for m in s.get("installed", []):
            self.installed.addItem(f"{m['name']}   {m['size'] / 1e9:.1f} GB")
            self.installed.item(self.installed.count() - 1).setData(Qt.ItemDataRole.UserRole, m["name"])
        if self.ctx.ai_setup_state.get("phase") in ("checking", "downloading"):
            self.ai_status.setText(self.ctx.ai_setup_state.get("message", "Local AI setup is running."))
        elif not self.ctx.status_checked:
            self.ai_status.setText("Not checked. The local AI remains dormant until you test or use it.")
        elif not s.get("running"):
            self.ai_status.setText(f"Offline. {s.get('error') or ''}")
        elif s.get("model_ready"):
            note = "" if s.get("preferred_installed") else f" (preferred model {s['preferred']} is not installed)"
            self.ai_status.setText(f"Connected. Using {s['active']}{note}.")
        else:
            self.ai_status.setText(f"Connected, but no model installed. Download {s['preferred']}.")

    def save_ai(self):
        self.db.set_ollama(host=self.host.text().strip().rstrip("/"), model=self.model.currentText().strip())
        self._start_ai_setup()

    def pull(self):
        model = self.model.currentText().strip()
        if not model:
            return
        self.db.set_ollama(host=self.host.text().strip().rstrip("/"), model=model)
        self._start_ai_setup()

    def _start_ai_setup(self):
        self.pull_btn.setEnabled(False)
        self.pull_bar.show()
        self.pull_bar.setRange(0, 0)
        self.pull_bar.setValue(0)
        self.pull_text.setText("Checking Ollama and downloading the model if needed…")
        self.ctx.ensure_ai_ready(force=True)

    def _setup_update(self, state):
        phase = state.get("phase")
        if phase == "downloading":
            percent = state.get("percent")
            if percent is not None:
                self.pull_bar.setValue(percent)
            self.pull_text.setText(state.get("status", state.get("message", "")))
        elif phase == "ready":
            self.pull_text.setText(state.get("message", "AI is ready."))
            self.pull_btn.setEnabled(True)
            self.pull_bar.hide()
        elif phase == "error":
            self.pull_text.setText(state.get("message", "AI setup failed."))
            self.pull_btn.setEnabled(True)
            self.pull_bar.hide()

    # ---- data ----
    def export(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export backup", "studios-backup.json", "JSON (*.json)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.db.export_all(), f, indent=2)
            self.ctx.toast.emit("Backup saved")

    def import_(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import backup", "", "JSON (*.json)")
        if path and confirm(self, "Importing replaces everything currently in StudiOS. Continue?", "Replace"):
            try:
                with open(path, encoding="utf-8") as f:
                    self.db.import_all(json.load(f))
            except (OSError, ValueError) as e:
                self.ctx.toast.emit(f"Import failed: {e}")
                return
            self.ctx.data_changed.emit("profile")
            self.refresh()

    def reset(self):
        if confirm(self, "Delete all courses, notes, tasks, quizzes and settings? This cannot be undone.", "Reset"):
            self.db.reset()
            self.ctx.shutdown_requested.emit()


