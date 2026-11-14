from PySide6.QtWidgets import QHBoxLayout, QListWidget, QProgressBar

from ... import config
from ..widgets import Panel, button, label, page_head
from .base import Page


class TerminalPage(Page):
    """Human-readable local AI setup and diagnostic console."""
    scroll = True

    def setup(self):
        self.root.addWidget(page_head(
            "System Setup", "StudiOS checks Ollama and downloads your selected model in the background."))
        status_panel = Panel("Local AI status")
        self.state_label = label("", "h2", wrap=True)
        self.progress = QProgressBar()
        self.progress.hide()
        self.log = QListWidget()
        self.retry_button = button("Check and set up AI", "primary", self.retry)
        self.download_button = button("Open Ollama setup page", None, self.open_download)
        actions = QHBoxLayout()
        actions.addWidget(self.retry_button)
        actions.addWidget(self.download_button)
        actions.addStretch(1)
        status_panel.body.addWidget(self.state_label)
        status_panel.body.addWidget(self.progress)
        status_panel.body.addWidget(label("Setup activity", muted=True))
        status_panel.body.addWidget(self.log)
        status_panel.body.addLayout(actions)
        status_panel.body.addWidget(label(
            f"Model: {config.DEFAULT_OLLAMA['model']}. The model files are downloaded once and reused; "
            "the model is only loaded into memory when you request AI output.",
            muted=True, wrap=True))
        self.root.addWidget(status_panel, 1)
        self.ctx.ai_setup_changed.connect(self.show_state)
        self.show_state(self.ctx.ai_setup_state)

    def refresh(self):
        self.show_state(self.ctx.ai_setup_state)

    def show_state(self, state):
        phase = state.get("phase", "idle")
        message = state.get("message", "AI setup has not run yet.")
        self.state_label.setText(message)
        self.progress.setVisible(phase in ("checking", "starting", "downloading"))
        if phase == "downloading":
            percent = state.get("percent")
            if percent is None:
                self.progress.setRange(0, 0)
            else:
                self.progress.setRange(0, 100)
                self.progress.setValue(percent)
        elif phase == "checking":
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, 100)
        self.retry_button.setEnabled(phase not in ("checking", "starting", "downloading"))
        if phase == "downloading":
            detail = message
            if state.get("status"):
                detail = f"{state['status']}" + (
                    f" · {state['percent']}%" if state.get("percent") is not None else "")
            if not self.log.count() or self.log.item(self.log.count() - 1).text() != detail:
                self.log.addItem(detail)
                self.log.scrollToBottom()
        elif phase in ("ready", "error"):
            if not self.log.count() or self.log.item(self.log.count() - 1).text() != message:
                self.log.addItem(message)
                self.log.scrollToBottom()

    def retry(self):
        self.ctx.ensure_ai_ready(force=True)

    def open_download(self):
        self.ctx.go("browser", url="https://ollama.com/download", title="Ollama setup")

