import tempfile
import unittest
from pathlib import Path

from StudiOS import config
from StudiOS.core.auth import hash_password, verify_password
from StudiOS.core.db import Database
from StudiOS.runtime import AppContext


class OsCoreTests(unittest.TestCase):
    def test_password_hash_is_salted_and_verified(self):
        salt, digest = hash_password("study-safe")
        other_salt, other_digest = hash_password("study-safe")
        self.assertNotEqual(salt, other_salt)
        self.assertNotEqual(digest, other_digest)
        self.assertTrue(verify_password("study-safe", salt, digest))
        self.assertFalse(verify_password("wrong", salt, digest))
        self.assertFalse(verify_password("study-safe", "", ""))

    def test_default_model_is_low_memory_qwen(self):
        self.assertEqual(config.DEFAULT_OLLAMA["model"], "qwen2.5:1.5b")
        self.assertEqual(config.DEFAULT_OLLAMA["fallback_models"], [])

    def test_existing_profiles_include_new_system_modules(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.db")
            db.kv_set("profile", {"name": "Asha", "modules": ["dashboard", "notes"]})
            modules = db.profile()["modules"]
            self.assertIn("browser", modules)
            self.assertIn("terminal", modules)
            self.assertNotIn("courses", modules)
            db.close()

    def test_database_filters_in_sql_and_preserves_false_values(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.db")
            done = db.add("tasks", title="Done", done=True)
            pending = db.add("tasks", title="Pending", done=False)
            self.assertEqual([task["id"] for task in db.list("tasks", done=False)], [pending["id"]])
            self.assertEqual([task["id"] for task in db.list("tasks", done=True)], [done["id"]])
            db.close()

    def test_app_context_does_not_probe_ollama_at_startup(self):
        with tempfile.TemporaryDirectory() as temp:
            ctx = AppContext(Path(temp))
            self.assertFalse(ctx.status_checked)
            self.assertFalse(ctx._status_pending)
            ctx.db.close()


if __name__ == "__main__":
    unittest.main()
