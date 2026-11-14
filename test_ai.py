import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

from StudiOS import config
from StudiOS.core.backend import BackendSetupError, LocalAIBackend
from StudiOS.core.ollama import OllamaClient, OllamaError


class OllamaOfflineTests(unittest.TestCase):
    def test_offline_status_and_chat_fail_gracefully(self):
        cfg = {**config.DEFAULT_OLLAMA, "host": "http://127.0.0.1:1"}
        client = OllamaClient(lambda: cfg)
        status = client.status()
        self.assertFalse(status["running"])
        self.assertIn("not running", status["error"].lower())
        with self.assertRaises(OllamaError):
            client.chat_stream([{"role": "user", "content": "hello"}])

    def test_installed_alternative_is_not_selected_automatically(self):
        class TagsHandler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                body = json.dumps({"models": [{"name": "llama3.2:1b"}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

        server = HTTPServer(("127.0.0.1", 0), TagsHandler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            cfg = {**config.DEFAULT_OLLAMA, "host": f"http://127.0.0.1:{server.server_port}"}
            status = OllamaClient(lambda: cfg).status()
            self.assertTrue(status["running"])
            self.assertFalse(status["model_ready"])
            self.assertIsNone(status["active"])
        finally:
            server.shutdown()
            server.server_close()

    def test_backend_pulls_configured_model_without_a_terminal(self):
        class FakeClient:
            def __init__(self):
                self.pulled = []

            def status(self):
                return {"running": True, "preferred_installed": bool(self.pulled),
                        "model_ready": bool(self.pulled),
                        "active": self.pulled[-1] if self.pulled else None}

            def pull(self, model, on_progress, stop):
                self.pulled.append(model)
                on_progress({"status": "success", "percent": 100})

        client = FakeClient()
        cfg = {**config.DEFAULT_OLLAMA}
        backend = LocalAIBackend(client, lambda: cfg)
        with patch.object(LocalAIBackend, "find_ollama", return_value="ollama.exe"):
            result = backend.ensure_ready()
        self.assertEqual(client.pulled, ["qwen2.5:1.5b"])
        self.assertTrue(result["model_ready"])

    def test_missing_ollama_runtime_reports_actionable_setup_error(self):
        backend = LocalAIBackend(OllamaClient(lambda: config.DEFAULT_OLLAMA),
                                 lambda: config.DEFAULT_OLLAMA)
        with patch.object(LocalAIBackend, "find_ollama", return_value=None):
            with self.assertRaisesRegex(BackendSetupError, "runtime was not found"):
                backend.ensure_ready()


if __name__ == "__main__":
    unittest.main()
