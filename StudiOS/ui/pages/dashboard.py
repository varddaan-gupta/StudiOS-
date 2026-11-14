from datetime import date, datetime
from PySide6.QtCore import QTimer

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from ...core import stats
from ..widgets import BarChart, Panel, StatCard, button, course_icon, label, page_head
from .base import DynamicPage


class DashboardPage(DynamicPage):
    def setup(self):
        super().setup()
        self.clock_timer = QTimer(self, interval=1000)
        self.clock_timer.timeout.connect(self._tick_widgets)
        self.clock_timer.start()

    def build(self, layout):
        db, p = self.db, self.db.profile()
        on = set(p["modules"])
        sub = " · ".join(x for x in [p["exam"], self._countdown(p)] if x) or "Here is your study day."
        layout.addWidget(page_head("Your workspace", sub))

        hero = QHBoxLayout()
        hero.setSpacing(16)
        clock_panel = Panel("Local time")
        self.digital_clock = label("", "statValue")
        self.digital_clock.setStyleSheet("font-size:48px;")
        self.digital_date = label("", muted=True)
        clock_panel.body.addWidget(self.digital_clock)
        clock_panel.body.addWidget(self.digital_date)
        hero.addWidget(clock_panel, 1)

        focus = Panel("Focus session")
        self.focus_time = label("", "statValue")
        self.focus_subject = QLineEdit(self.ctx.timer.subject or "", placeholderText="Study subject")
        self.focus_status = label("", muted=True)
        focus_actions = QHBoxLayout()
        self.focus_start_btn = button("Start focus", "primary", self._start_focus)
        focus_actions.addWidget(self.focus_start_btn)
        focus_actions.addWidget(button("Pause", None, self._pause_focus))
        focus_actions.addWidget(button("Finish", "ghost", self._stop_focus))
        focus.body.addWidget(self.focus_time)
        focus.body.addWidget(self.focus_subject)
        focus.body.addWidget(self.focus_status)
        focus.body.addLayout(focus_actions)
        hero.addWidget(focus, 1)

        tip = Panel("AI study insight")
        self.tip_text = label(self.ctx.latest_study_tip, muted=True, wrap=True)
        tip.body.addWidget(self.tip_text, 1)
        tip.body.addWidget(button("Open assistant", "link", lambda: self.ctx.go("assistant")))
        hero.addWidget(tip, 1)
        layout.addLayout(hero)
        self._tick_widgets()

        # Row of readouts
        done, total = stats.tasks_done(db)
        quiz = stats.quiz_average(db)
        row = QHBoxLayout()
        row.setSpacing(16)
        for value, cap in [
            (f"{stats.minutes_today(db)}m", "studied today"),
            (f"{total - done}", "tasks pending"),
            (f"{quiz}%" if quiz is not None else "-", "quiz average"),
            (f"{stats.streak(db)}d", "study streak"),
        ]:
            row.addWidget(StatCard(value, cap))
        layout.addLayout(row)

        grid = QGridLayout()
        grid.setSpacing(16)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        cards = []
        if "courses" in on:
            cards.append((self._courses(), True))
        if "planner" in on:
            cards.append((self._plan(), False))
        if "tasks" in on:
            cards.append((self._tasks(), False))
        if "notes" in on:
            cards.append((self._notes(), False))
        if "progress" in on:
            cards.append((self._chart(), False))
        if "assistant" in on:
            cards.append((self._ask(), False))
        r = c = 0
        for card, wide in cards:
            if wide:
                if c:
                    r, c = r + 1, 0
                grid.addWidget(card, r, 0, 1, 2)
                r += 1
            else:
                grid.addWidget(card, r, c)
                c += 1
                if c == 2:
                    r, c = r + 1, 0
        layout.addLayout(grid)

    def _tick_widgets(self):
        now = datetime.now()
        if hasattr(self, "digital_clock"):
            self.digital_clock.setText(now.strftime("%H:%M:%S"))
            self.digital_date.setText(now.strftime("%A, %d %B %Y"))
            self.tip_text.setText(self.ctx.latest_study_tip)
            timer = self.ctx.timer
            elapsed = timer.elapsed()
            self.focus_time.setText(f"{elapsed // 3600:02d}:{elapsed % 3600 // 60:02d}:{elapsed % 60:02d}")
            self.focus_status.setText(
                f"{timer.state.title()}" + (f" · {timer.subject}" if timer.subject else " · Ready when you are"))
            self.focus_start_btn.setText("Resume focus" if timer.state == "paused" else "Start focus")

    def _start_focus(self):
        self.ctx.timer.start(self.focus_subject.text().strip() or "Study")
        self._tick_widgets()

    def _pause_focus(self):
        self.ctx.timer.pause()
        self._tick_widgets()

    def _stop_focus(self):
        subject, minutes = self.ctx.timer.stop()
        if minutes:
            self.db.add("sessions", date=date.today().isoformat(), minutes=minutes, subject=subject)
            self.ctx.data_changed.emit("sessions")
            self.ctx.toast.emit(f"Logged {minutes} min of {subject}")
        self._tick_widgets()

    @staticmethod
    def _countdown(p):
        try:
            days = (date.fromisoformat(p["exam_date"]) - date.today()).days
        except ValueError:
            return ""
        return f"{days} days to exam" if days >= 0 else ""

    def _link(self, panel, text, page):
        panel.body.addWidget(button(text, "link", lambda: self.ctx.go(page)))

    def _courses(self):
        panel = Panel("Courses", button("Manage", "link", lambda: self.ctx.go("courses")))
        courses = self.db.list("courses")
        if not courses:
            panel.body.addWidget(label("No courses yet. Add your first one to get a launcher here.", muted=True))
            return panel
        row = QHBoxLayout()
        row.setSpacing(18)
        for c in courses[:8]:
            col = QVBoxLayout()
            col.setSpacing(4)
            icon = course_icon(self.ctx, c, 52)
            icon.setCursor(Qt.PointingHandCursor)
            icon.mousePressEvent = lambda e, cc=c: self.ctx.go("courses")
            col.addWidget(icon, 0, Qt.AlignHCenter)
            name = label(c["title"][:14], muted=True)
            name.setAlignment(Qt.AlignHCenter)
            col.addWidget(name)
            row.addLayout(col)
        row.addStretch(1)
        panel.body.addLayout(row)
        return panel

    def _plan(self):
        panel = Panel("Today's plan", button("Planner", "link", lambda: self.ctx.go("planner")))
        today = date.today().isoformat()
        blocks = sorted((b for b in self.db.list("blocks") if b["date"] == today), key=lambda b: b["start"])
        if not blocks:
            panel.body.addWidget(label("Nothing scheduled today.", muted=True))
        for b in blocks[:5]:
            panel.body.addWidget(label(f"{b['start']}   {b['subject']}  ({b['minutes']} min)"))
        return panel

    def _tasks(self):
        panel = Panel("Priority tasks", button("Tasks", "link", lambda: self.ctx.go("tasks")))
        rank = {"High": 0, "Medium": 1, "Low": 2}
        pending = sorted((t for t in self.db.list("tasks") if not t.get("done")),
                         key=lambda t: (rank.get(t.get("priority"), 1), t.get("due") or "9999"))
        if not pending:
            panel.body.addWidget(label("All clear.", muted=True))
        for t in pending[:5]:
            row = QHBoxLayout()
            row.addWidget(label(t["title"]), 1)
            row.addWidget(label(t.get("priority", "Medium"),
                                chip={"High": "bad", "Medium": "warn"}.get(t.get("priority"), "true")))
            panel.body.addLayout(row)
        return panel

    def _notes(self):
        panel = Panel("Recent notes", button("Notes", "link", lambda: self.ctx.go("notes")))
        notes = sorted(self.db.list("notes"), key=lambda n: n["updated"], reverse=True)
        if not notes:
            panel.body.addWidget(label("No notes yet.", muted=True))
        for n in notes[:4]:
            panel.body.addWidget(button(n["title"] or "Untitled", "link",
                                        lambda nid=n["id"]: self.ctx.go("notes", note_id=nid)))
        return panel

    def _chart(self):
        panel = Panel("Last 7 days (minutes)", button("Progress", "link", lambda: self.ctx.go("progress")))
        panel.body.addWidget(BarChart(stats.last_days(self.db)))
        return panel

    def _ask(self):
        panel = Panel("Ask the assistant")
        s = self.ctx.status
        if s.get("model_ready"):
            message = f"Model ready: {s['active']}"
        elif self.ctx.ai_setup_state.get("phase") in ("checking", "downloading"):
            message = "StudiOS is preparing the local AI in the background."
        elif not self.ctx.status_checked:
            message = "Local AI setup will start automatically."
        else:
            message = "AI is offline. Open System Setup to retry."
        panel.body.addWidget(label(message, muted=True))
        edit = QLineEdit()
        edit.setPlaceholderText("Type a doubt and press Enter")
        edit.returnPressed.connect(lambda: self.ctx.go("assistant", prefill=edit.text(), send=True))
        panel.body.addWidget(edit)
        return panel
