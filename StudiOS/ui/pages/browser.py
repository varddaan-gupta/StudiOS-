from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QProgressBar, QVBoxLayout

from ..widgets import Panel, button, page_head
from .base import Page


def course_url(value):
    text = (value or "").strip()
    if text and "://" not in text:
        text = "https://" + text
    url = QUrl(text)
    if url.scheme().lower() not in ("http", "https") or not url.host():
        raise ValueError("Enter a complete HTTP or HTTPS course link.")
    return url


class BrowserPage(Page):
    """Lazy native in-app browser for course websites."""
    scroll = False

    def setup(self):
        self.root.addWidget(page_head("StudiOS Browser", "Course pages stay inside your study workspace."))
        panel = Panel()
        controls = QHBoxLayout()
        self.back_button = button("‹", "ghost", self._back, "sm")
        self.forward_button = button("›", "ghost", self._forward, "sm")
        self.reload_button = button("↻", "ghost", self._reload, "sm")
        self.address = QLineEdit(placeholderText="Paste a course URL and press Enter")
        self.address.returnPressed.connect(self.navigate)
        controls.addWidget(self.back_button)
        controls.addWidget(self.forward_button)
        controls.addWidget(self.reload_button)
        controls.addWidget(self.address, 1)
        controls.addWidget(button("Go", "primary", self.navigate))
        panel.body.addLayout(controls)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setFixedHeight(5)
        panel.body.addWidget(self.progress)
        self.browser_host = QVBoxLayout()
        panel.body.addLayout(self.browser_host, 1)
        self.root.addWidget(panel, 1)
        self.view = None

    def _ensure_view(self):
        if self.view is not None:
            return
        from PySide6.QtWebEngineWidgets import QWebEngineView

        self.view = QWebEngineView(self)
        self.view.urlChanged.connect(self._url_changed)
        self.view.loadProgress.connect(self.progress.setValue)
        self.view.loadFinished.connect(self._load_finished)
        self.browser_host.addWidget(self.view)

    def refresh(self):
        self._ensure_view()
        target = self.ctx.handoff.pop("url", None)
        self.ctx.handoff.pop("title", None)
        if target:
            try:
                url = course_url(target)
            except ValueError as error:
                self.ctx.toast.emit(str(error))
                return
            view = self.view
            if view is not None and view.url() != url:
                view.setUrl(url)
        elif self.view is not None and not self.view.url().isValid():
            self.address.setText("")

    def navigate(self):
        try:
            url = course_url(self.address.text())
        except ValueError as error:
            self.ctx.toast.emit(str(error))
            return
        self._ensure_view()
        view = self.view
        if view is not None:
            view.setUrl(url)

    def _url_changed(self, url):
        self.address.setText(url.toString())

    def _load_finished(self, ok):
        self.progress.setValue(100)
        view = self.view
        if view is None:
            return
        self.back_button.setEnabled(view.history().canGoBack())
        self.forward_button.setEnabled(view.history().canGoForward())
        if not ok:
            self.ctx.toast.emit("This page could not be loaded. Check the link or your connection.")

    def _back(self):
        if self.view:
            self.view.back()

    def _forward(self):
        if self.view:
            self.view.forward()

    def _reload(self):
        if self.view:
            self.view.reload()
