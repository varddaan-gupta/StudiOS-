"""Discover and prepare the local Ollama runtime without opening a terminal."""
import os
import shutil
import subprocess
import time
from pathlib import Path

from .ollama import OllamaError


class BackendSetupError(RuntimeError):
    pass


class LocalAIBackend:
    def __init__(self, client, get_cfg, popen=subprocess.Popen, sleep=time.sleep):
        self.client = client
        self.get_cfg = get_cfg
        self._popen = popen
        self._sleep = sleep
        self.server_process = None

    @staticmethod
    def find_ollama():
        configured = os.environ.get("OLLAMA_EXE")
        candidates: list[str | Path | None] = [configured, shutil.which("ollama")]
        if os.name == "nt":
            local = os.environ.get("LOCALAPPDATA")
            program_files = os.environ.get("ProgramFiles")
            candidates.extend([
                Path(local) / "Programs" / "Ollama" / "ollama.exe" if local else None,
                Path(program_files) / "Ollama" / "ollama.exe" if program_files else None,
            ])
        else:
            candidates.extend([Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama")])
        return next((str(path) for path in candidates if path and Path(path).is_file()), None)

    def _start_server(self, executable):
        kwargs = {"stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL,
                  "stderr": subprocess.DEVNULL, "close_fds": True}
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            self.server_process = self._popen([executable, "serve"], **kwargs)
        except OSError as error:
            raise BackendSetupError(f"Could not start the local AI service: {error}") from error

    def ensure_ready(self, on_progress=lambda _progress: None, stop=lambda: False,
                     on_status=lambda _status: None):
        executable = self.find_ollama()
        if not executable:
            raise BackendSetupError(
                "The local Ollama runtime was not found. Use System Setup to open the official "
                "installer, then retry. StudiOS will download the selected model automatically.")

        status = self.client.status()
        if not status["running"]:
            self._start_server(executable)
            for _ in range(30):
                if stop():
                    raise BackendSetupError("AI setup was cancelled.")
                self._sleep(1)
                status = self.client.status()
                if status["running"]:
                    break
            if not status["running"]:
                raise BackendSetupError(
                    "Ollama was found but did not start. Check whether another Ollama service is "
                    "using this address, then retry.")

        if stop():
            raise BackendSetupError("AI setup was cancelled.")
        if not status.get("preferred_installed"):
            model = self.get_cfg()["model"]
            on_status({"phase": "downloading", "message": f"Downloading {model} in the background…"})
            try:
                self.client.pull(model, on_progress, stop)
            except OllamaError as error:
                raise BackendSetupError(f"Could not download {model}: {error}") from error

        status = self.client.status()
        if not status.get("model_ready"):
            raise BackendSetupError(
                f"The local runtime is ready, but {status.get('preferred')} is not available yet.")
        on_status({"phase": "ready", "message": f"{status['active']} is ready."})
        return status

