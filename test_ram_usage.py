"""Local RSS diagnostic: python test_ram_usage.py

The app's RSS and (when detectable) Ollama's RSS are reported separately because the model
runs in Ollama's process, not in StudiOS.
"""
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication

from StudiOS.core.auth import hash_password
from StudiOS.core.ollama import OllamaError
from StudiOS.runtime import AppContext
from StudiOS.ui.main_window import MainWindow


def rss_mb():
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        class Counters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL("Kernel32.dll")
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        process = kernel.GetCurrentProcess()
        psapi = ctypes.WinDLL("Psapi.dll")
        get_info = psapi.GetProcessMemoryInfo
        get_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        get_info.restype = wintypes.BOOL
        if get_info(process, ctypes.byref(counters), counters.cb):
            return counters.WorkingSetSize / (1024 * 1024)
        command = f"(Get-Process -Id {os.getpid()}).WorkingSet64"
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command], text=True, timeout=5,
            stderr=subprocess.DEVNULL).strip()
        return int(output) / (1024 * 1024)
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        import resource
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / (1024 * 1024 if sys.platform == "darwin" else 1024)


def ollama_rss_mb():
    if os.name != "nt":
        return None
    command = (
        "$p=Get-Process -ErrorAction SilentlyContinue | Where-Object {$_.ProcessName -like 'ollama*'}; "
        "if ($p) {[int64](($p | Measure-Object -Property WorkingSet64 -Sum).Sum)} else {0}"
    )
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command], text=True, timeout=5,
            stderr=subprocess.DEVNULL).strip()
        return int(output or 0) / (1024 * 1024)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def webengine_rss_mb():
    if os.name != "nt":
        return None
    command = (
        "$p=Get-Process -ErrorAction SilentlyContinue | "
        "Where-Object {$_.ProcessName -like '*QtWebEngineProcess*'}; "
        "if ($p) {[int64](($p | Measure-Object -Property WorkingSet64 -Sum).Sum)} else {0}"
    )
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command], text=True, timeout=5,
            stderr=subprocess.DEVNULL).strip()
        return int(output or 0) / (1024 * 1024)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main():
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as temp:
        ctx = AppContext(Path(temp))
        salt, digest = hash_password("1234")
        ctx.db.set_profile(name="Diagnostic", setup_complete=True, password_salt=salt, password_hash=digest)
        window = MainWindow(ctx)
        try:
            window.show()
            window.lock_screen.password.setText("1234")
            window.lock_screen.unlock()
            app.processEvents()
            time.sleep(.2)
            baseline = rss_mb()
            window.go("notes")
            app.processEvents()
            notes_rss = rss_mb()
            window.go("assistant")
            app.processEvents()
            before_ai = rss_mb()

            ai_result = "skipped (Ollama/model unavailable)"
            try:
                status = ctx.ollama.status()
                if status["model_ready"]:
                    received = []
                    ctx.ollama.chat_stream(
                        [{"role": "user", "content": "Reply with one short word: ready"}],
                        lambda token: received.append(token), lambda: bool(received))
                    ai_result = f"called {status['active']}"
            except OllamaError as error:
                ai_result = f"unavailable ({error})"

            app.processEvents()
            after_ai = rss_mb()
            engine = ollama_rss_mb()
            window.go("browser")
            app.processEvents()
            time.sleep(.5)
            browser_app = rss_mb()
            browser_engine = webengine_rss_mb()
        finally:
            window.close()
            ctx.db.close()

    print("StudiOS RAM diagnostic (working set)")
    print(f"Baseline desktop: {baseline:.0f} MB")
    print(f"With Notes + AI view: {before_ai:.0f} MB (Notes view: {notes_rss:.0f} MB)")
    print(f"After AI request: {after_ai:.0f} MB — {ai_result}")
    if engine is not None and engine:
        print(f"Ollama process group: {engine:.0f} MB")
        print(f"App + Ollama total: {after_ai + engine:.0f} MB")
    print(f"With embedded Browser: app {browser_app:.0f} MB" +
          (f" + WebEngine {browser_engine:.0f} MB" if browser_engine is not None else ""))
    browser_total = browser_app + (browser_engine or 0)
    ai_total = after_ai + (engine or 0)
    app_ok = baseline < 500 and browser_total < 1000
    print(f"App and browser memory: {'PASS' if app_ok else 'REVIEW'} "
          "(targets: baseline <500 MB; browser process group <1 GB)")
    if ai_result.startswith("called "):
        print(f"AI memory: {'PASS' if ai_total < 4096 else 'REVIEW'} "
              f"(app + Ollama {ai_total:.0f} MB; 4 GB target)")
    else:
        print(f"AI memory: NOT TESTED — {ai_result}")


if __name__ == "__main__":
    main()
