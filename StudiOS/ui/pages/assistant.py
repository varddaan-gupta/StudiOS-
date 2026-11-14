import html
import re
import uuid

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QTextBrowser,
)

from ...core.context import build_system_prompt
from ..theme import C
from ..widgets import Panel, button, label, page_head
from .base import Page


def md_to_html(text):
    """Tiny markdown subset: code, bold, bullets, line breaks."""
    t = html.escape(text)
    t = re.sub(r"```(?:\w+)?\n?(.*?)```", r"<pre>\1</pre>", t, flags=re.S)
    t = re.sub(r"`([^`]+)`", r"<code>\1</code>", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?m)^\s*[-*] ", "&bull; ", t)
    return t.replace("\n", "<br>")


class AssistantPage(Page):
    scroll = False

    def setup(self):
        self.history, self.worker = [], None
        self.current_chat = None
        self.root.addWidget(page_head("Assistant", "Answers come from your active course and the notes you tick."))
        row = QHBoxLayout()
        row.setSpacing(16)
        self.root.addLayout(row, 1)

        # context column
        side = Panel("Context")
        side.setFixedWidth(280)
        side.body.addWidget(label("Recent chats", muted=True))
        self.chat_list = QListWidget()
        self.chat_list.currentItemChanged.connect(self._select_chat)
        side.body.addWidget(self.chat_list, 1)
        self.new_chat_button = button("New chat", "ghost", self.clear)
        side.body.addWidget(self.new_chat_button)
        side.body.addWidget(label("Ground answers in", muted=True))
        self.course = QComboBox()
        self.subject = QLineEdit(placeholderText="Subject (optional)")
        self.notes = QListWidget()
        side.body.addWidget(label("Course", muted=True))
        side.body.addWidget(self.course)
        side.body.addWidget(self.subject)
        side.body.addWidget(label("Notes to rely on", muted=True))
        side.body.addWidget(self.notes, 1)
        row.addWidget(side)

        # chat column
        chat = Panel()
        self.banner = label("", chip="bad", wrap=True)
        self.view = QTextBrowser()
        self.view.document().setDefaultStyleSheet(
            f"pre{{background:{C['ground']};}} code{{color:{C['accent2']};}}")
        self.input = QLineEdit(placeholderText="Ask a doubt, request a summary, or a formula breakdown")
        self.input.returnPressed.connect(self.send)
        self.send_btn = button("Send", "primary", self.send)
        self.stop_btn = button("Stop", None, self.stop)
        self.stop_btn.hide()
        bar = QHBoxLayout()
        bar.addWidget(self.input, 1)
        bar.addWidget(self.send_btn)
        bar.addWidget(self.stop_btn)
        chat.body.addWidget(self.banner)
        chat.body.addWidget(self.view, 1)
        chat.body.addLayout(bar)
        row.addWidget(chat, 1)
        self.render()
        self._refresh_chats()

    def refresh(self):
        keep = {self.notes.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.notes.count())
                if self.notes.item(i).checkState() == Qt.CheckState.Checked}
        h = self.ctx.handoff
        keep |= set(h.pop("note_ids", []))
        cur_course = h.pop("course_id", None) or self.course.currentData()
        self.course.clear()
        self.course.addItem("No course", "")
        for c in self.db.list("courses"):
            self.course.addItem(c["title"], c["id"])
        self.course.setCurrentIndex(max(self.course.findData(cur_course), 0))
        self.notes.clear()
        for n in self.db.list("notes"):
            it = QListWidgetItem(n["title"] or "Untitled")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if n["id"] in keep else Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, n["id"])
            self.notes.addItem(it)
        s = self.ctx.status
        self.update_status(s)
        self._refresh_chats()
        if (pre := h.pop("prefill", None)):
            self.input.setText(pre)
            if h.pop("send", False):
                self.send()

    def update_status(self, status):
        self.banner.setVisible(not status.get("model_ready"))
        if status.get("model_ready"):
            self.banner.setText("")
        elif self.ctx.ai_setup_state.get("phase") in ("checking", "downloading"):
            self.banner.setText("StudiOS is preparing the local AI in the background. See System Setup for progress.")
        elif not self.ctx.status_checked:
            self.banner.setText("AI status will be checked automatically.")
        else:
            self.banner.setText(status.get("error") or "Open System Setup to retry local AI setup.")

    def _refresh_chats(self, selected=None):
        self.chat_records = self.db.kv_get("ai_chats", [])
        self.chat_list.blockSignals(True)
        self.chat_list.clear()
        for chat in self.chat_records:
            item = QListWidgetItem(chat.get("title") or "New chat")
            item.setData(Qt.ItemDataRole.UserRole, chat.get("id"))
            self.chat_list.addItem(item)
            if chat.get("id") == (selected or self.current_chat):
                self.chat_list.setCurrentItem(item)
        self.chat_list.blockSignals(False)

    def _select_chat(self, item, _previous):
        if not item or self.worker:
            return
        chat_id = item.data(Qt.ItemDataRole.UserRole)
        if chat_id == self.current_chat:
            return
        self._persist_chat()
        record = next((chat for chat in self.chat_records if chat.get("id") == chat_id), None)
        if record:
            self.current_chat = chat_id
            self.history = list(record.get("messages", []))
            self.render()

    def _persist_chat(self):
        if not self.history:
            return
        records = self.db.kv_get("ai_chats", [])
        title = next((m["content"].strip() for m in self.history if m.get("role") == "user"), "New chat")
        title = (title[:42] + "…") if len(title) > 42 else title
        record = {"id": self.current_chat or uuid.uuid4().hex, "title": title,
                  "messages": self.history[-40:]}
        self.current_chat = record["id"]
        records = [chat for chat in records if chat.get("id") != self.current_chat]
        records.insert(0, record)
        self.db.kv_set("ai_chats", records[:30])
        self._refresh_chats(self.current_chat)

    def _context(self):
        course = self.db.get("courses", self.course.currentData()) if self.course.currentData() else None
        notes = [self.db.get("notes", self.notes.item(i).data(Qt.ItemDataRole.UserRole))
                 for i in range(self.notes.count())
                 if self.notes.item(i).checkState() == Qt.CheckState.Checked]
        return build_system_prompt(self.db.profile()["exam"], course, self.subject.text().strip() or None,
                                   [n for n in notes if n])

    def render(self):
        if not self.history:
            self.view.setHtml(f"<p style='color:{C['muted']}'>Ask anything about what you are studying. "
                              "Tick notes on the left and the answer will stay grounded in them.</p>")
            return
        parts = []
        for m in self.history:
            you = m["role"] == "user"
            bg, who = (C["panel2"], "You") if you else (C["ground"], "StudiOS")
            colour = C["bad"] if m.get("error") else C["text"]
            parts.append(
                f"<table width='100%' cellpadding='10' cellspacing='0' style='margin-bottom:8px'><tr>"
                f"<td bgcolor='{bg}'><span style='color:{C['accent']}'><b>{who}</b></span><br>"
                f"<span style='color:{colour}'>{md_to_html(m['content']) or '...'}</span></td></tr></table>")
        self.view.setHtml("".join(parts))
        self.view.verticalScrollBar().setValue(self.view.verticalScrollBar().maximum())

    def send(self):
        text = self.input.text().strip()
        if not text or self.worker:
            return
        self.input.clear()
        if not self.current_chat:
            self.current_chat = uuid.uuid4().hex
        self.history += [{"role": "user", "content": text}, {"role": "assistant", "content": ""}]
        self._persist_chat()
        self.render()
        msgs = [{"role": "system", "content": self._context()},
                *[{"role": m["role"], "content": m["content"]} for m in self.history[:-1][-10:]]]
        self.send_btn.hide()
        self.stop_btn.show()
        self.chat_list.setEnabled(False)
        self.new_chat_button.setEnabled(False)
        self.worker = self.ctx.run(
            lambda w: self.ctx.ollama.chat_stream(msgs, w.token.emit, lambda: w.stopped),
            on_token=self._token, on_done=lambda _r: self._finish(), on_fail=self._fail)

    def _token(self, t):
        if not self.history or self.history[-1].get("role") != "assistant":
            return
        self.history[-1]["content"] += t
        self.render()

    def _fail(self, msg):
        if self.history and self.history[-1].get("role") == "assistant":
            self.history[-1].update(content=msg, error=True)
        self._finish()

    def _finish(self):
        self.worker = None
        self.send_btn.show()
        self.stop_btn.hide()
        self.chat_list.setEnabled(True)
        self.new_chat_button.setEnabled(True)
        self._persist_chat()
        answer = self.history[-1].get("content", "").strip() if self.history else ""
        if answer and not self.history[-1].get("error"):
            self.ctx.latest_study_tip = answer[:180]
        self.render()

    def stop(self):
        if self.worker:
            self.worker.stop()

    def clear(self):
        self.stop()
        self.history = []
        self.current_chat = None
        self.chat_list.clearSelection()
        self.render()
