"""Shared app state, background workers and the study timer."""
import time

from PySide6.QtCore import QObject, QThread, Signal, QTimer
from PySide6.QtGui import QPixmap
from shiboken6 import isValid

from . import config
from .core.backend import LocalAIBackend
from .core import favicons
from .core.db import Database
from .core.ollama import OllamaClient


class Worker(QThread):
    """Runs fn(worker) off the UI thread. fn may emit worker.token / worker.progress."""
    token = Signal(str)
    progress = Signal(dict)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn
        self._stop = False

    def stop(self):
        self._stop = True

    @property
    def stopped(self):
        return self._stop

    def run(self):
        try:
            result = self.fn(self)
        except Exception as e:  # shown to the user, never crashes the app
            self.failed.emit(str(e) or e.__class__.__name__)
        else:
            self.done.emit(result)


class StudyTimer:
    """Stopwatch that survives page changes."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.subject, self.state, self._acc, self._t0 = "", "idle", 0.0, 0.0

    def start(self, subject=""):
        if self.state == "idle":
            self.subject = subject
        self._t0, self.state = time.monotonic(), "running"

    def pause(self):
        if self.state == "running":
            self._acc += time.monotonic() - self._t0
            self.state = "paused"

    def elapsed(self):
        return int(self._acc + (time.monotonic() - self._t0 if self.state == "running" else 0))

    def stop(self):
        """Returns (subject, minutes) and resets."""
        self.pause()
        subject, secs = self.subject, self.elapsed()
        self.reset()
        return subject, (max(1, round(secs / 60)) if secs >= 30 else 0)


class AppContext(QObject):
    navigate = Signal(str)        # page id
    status_changed = Signal(dict)  # Ollama status
    data_changed = Signal(str)     # "profile", "courses", ...
    toast = Signal(str)
    shutdown_requested = Signal()
    ai_setup_changed = Signal(dict)

    def __init__(self, data_dir=None):
        super().__init__()
        self.db = Database((data_dir or config.DATA_DIR) / "studios.db")
        self.ollama = OllamaClient(self.db.ollama_cfg)
        self.backend = LocalAIBackend(self.ollama, self.db.ollama_cfg)
        self.status = {"running": False, "model_ready": False, "active": None, "error": "Checking..."}
        self.status_checked = False
        self._status_pending = False
        self._ai_setup_pending = False
        self.ai_setup_state = {"phase": "idle", "message": "AI setup has not run yet."}
        self.latest_study_tip = "Your latest AI tip or generated quiz will appear here."
        self.handoff = {}  # data passed from one page to the next
        self.timer = StudyTimer()
        self._keep = set()

    def run(self, fn, on_done=None, on_fail=None, on_token=None, on_progress=None):
        w = Worker(fn)
        self._keep.add(w)
        if on_done:
            w.done.connect(on_done)
        if on_fail:
            w.failed.connect(on_fail)
        if on_token:
            w.token.connect(on_token)
        if on_progress:
            w.progress.connect(on_progress)
        w.finished.connect(lambda: self._keep.discard(w))
        w.start()
        return w

    def refresh_status(self):
        if self._status_pending:
            return
        self._status_pending = True
        def done(s):
            self.status = s
            self.status_checked = True
            self._status_pending = False
            self.status_changed.emit(s)
        def fail(message):
            self._status_pending = False
            self.status = {"running": False, "model_ready": False, "active": None,
                           "error": message, "installed": []}
            self.status_checked = True
            self.status_changed.emit(self.status)
        self.run(lambda w: self.ollama.status(), on_done=done, on_fail=fail)

    def ensure_ai_status(self):
        if not self.status_checked and not self._status_pending and not self._ai_setup_pending:
            self.refresh_status()

    def ensure_ai_ready(self, force=False):
        if self._ai_setup_pending or (self.ai_setup_state["phase"] == "ready" and not force):
            return
        self._ai_setup_pending = True
        self.ai_setup_state = {"phase": "checking", "message": "Checking the local AI runtime…"}
        self.ai_setup_changed.emit(dict(self.ai_setup_state))

        def progress(value):
            state = {"phase": "downloading", **value}
            self.ai_setup_state = state
            self.ai_setup_changed.emit(dict(state))

        def status(value):
            self.ai_setup_state = dict(value)
            self.ai_setup_changed.emit(dict(value))

        def done(result):
            self._ai_setup_pending = False
            self.status = result
            self.status_checked = True
            self.ai_setup_state = {"phase": "ready", "message": f"{result['active']} is ready."}
            self.db.kv_set("ai_setup", dict(self.ai_setup_state))
            self.status_changed.emit(result)
            self.ai_setup_changed.emit(dict(self.ai_setup_state))

        def fail(message):
            self._ai_setup_pending = False
            self.status = {"running": False, "model_ready": False, "active": None,
                           "preferred": self.db.ollama_cfg()["model"], "error": message, "installed": []}
            self.status_checked = True
            self.ai_setup_state = {"phase": "error", "message": message}
            self.db.kv_set("ai_setup", dict(self.ai_setup_state))
            self.status_changed.emit(self.status)
            self.ai_setup_changed.emit(dict(self.ai_setup_state))

        self.run(
            lambda worker: self.backend.ensure_ready(
                lambda value: worker.progress.emit(value),
                lambda: worker.stopped,
                lambda value: worker.progress.emit(value)),
            on_done=done, on_fail=fail,
            on_progress=lambda value: status(value) if value.get("phase") else progress(value))

    def go(self, page, **handoff):
        self.handoff = handoff
        self.navigate.emit(page)

    def favicon(self, url, label, size=44):
        """Fills a QLabel with the course logo when it is ready."""
        def apply(path):
            if path and isValid(label):
                pm = QPixmap(str(path))
                if not pm.isNull():
                    label.setText("")
                    label.setPixmap(pm.scaled(size - 12, size - 12))
        if (hit := favicons.cached(url)):
            apply(hit)
        elif url:
            self.run(lambda w: favicons.fetch(url), on_done=apply)
