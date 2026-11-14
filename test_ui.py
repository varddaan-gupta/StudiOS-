import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from StudiOS.core.auth import hash_password
from StudiOS.core.auth import verify_password
from StudiOS.runtime import AppContext
from StudiOS.ui.main_window import MainWindow
from StudiOS.ui.pages import PAGES
from StudiOS.ui.pages.browser import course_url
from StudiOS.ui.pages.settings import SettingsPage
from StudiOS.ui.pages.wizard import SetupWizard


class OsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_lock_screen_and_lazy_dock_navigation(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = AppContext(Path(temp))
            salt, digest = hash_password("1234")
            ctx.db.set_profile(name="Asha", setup_complete=True, password_salt=salt, password_hash=digest)
            ctx.refresh_status = lambda: None
            window = MainWindow(ctx)
            try:
                self.assertTrue(window.windowFlags() & Qt.WindowType.FramelessWindowHint)
                self.assertIs(window.shell_stack.currentWidget(), window.lock_screen)
                self.assertEqual(set(window.pages), {"dashboard"})
                self.assertEqual(len(window.buttons), len(PAGES))
                window.go("notes")
                self.assertNotIn("notes", window.pages)

                window.lock_screen.password.setText("1234")
                window.lock_screen.unlock()
                self.app.processEvents()
                self.assertIs(window.shell_stack.currentWidget(), window.desktop)
                window.buttons["notes"].click()
                self.app.processEvents()
                self.assertEqual(window.stack.currentWidget(), window.holders["notes"])
                self.assertIn("notes", window.pages)
                self.assertNotIn("assistant", window.pages)

                window.buttons["assistant"].click()
                self.app.processEvents()
                self.assertEqual(window.stack.currentWidget(), window.holders["assistant"])
                self.assertIn("assistant", window.pages)
                self.assertNotIn("browser", window.pages)
                window.buttons["browser"].click()
                self.app.processEvents()
                self.assertIsNotNone(window.pages["browser"].view)
                window.lock()
                window.go("dashboard")
                self.assertIs(window.shell_stack.currentWidget(), window.lock_screen)
            finally:
                window.close()
                ctx.db.close()

    def test_browser_urls_stay_in_app_and_reject_non_web_schemes(self):
        self.assertEqual(course_url("example.com/course").toString(), "https://example.com/course")
        with self.assertRaises(ValueError):
                course_url("file:///C:/Users/student/private.txt")

    def test_reset_requests_shutdown_instead_of_reopening_oobe(self):
        with tempfile.TemporaryDirectory() as temp:
                ctx = AppContext(Path(temp))
                ctx.db.set_profile(name="Asha", setup_complete=True)
                page = SettingsPage(ctx)
                requested = []
                ctx.shutdown_requested.connect(lambda: requested.append(True))
                with patch("StudiOS.ui.pages.settings.confirm", return_value=True):
                    page.reset()
                self.assertEqual(requested, [True])
                self.assertFalse(ctx.db.profile()["setup_complete"])
                ctx.db.close()

    def test_oobe_saves_password_and_default_local_model_without_probing(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = AppContext(Path(temp))
            wizard = SetupWizard(ctx)
            wizard.name.setText("Asha")
            wizard.password.setText("1234")
            wizard.password_confirm.setText("1234")
            wizard.finish()
            profile = ctx.db.profile()
            self.assertEqual(profile["name"], "Asha")
            self.assertTrue(verify_password("1234", profile["password_salt"], profile["password_hash"]))
            self.assertEqual(ctx.db.ollama_cfg()["model"], "qwen2.5:1.5b")
            self.assertFalse(ctx.status_checked)
            ctx.db.close()


if __name__ == "__main__":
    unittest.main()
