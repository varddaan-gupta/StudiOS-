"""Download qwen2.5:1.5b, or a requested model.   python scripts/setup_ollama.py [model]"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from StudiOS import config
from StudiOS.core.db import Database
from StudiOS.core.ollama import OllamaClient

db = Database(config.DATA_DIR / "studios.db")
cfg = {**config.DEFAULT_OLLAMA, **db.kv_get("ollama", {})}
db.close()
if len(sys.argv) > 1:
    cfg["model"] = sys.argv[1]
cli = OllamaClient(lambda: cfg)
s = cli.status()
if not s["running"]:
    sys.exit("\nOllama is not running.\n  1. Install it from https://ollama.com/download\n"
             "  2. Start the Ollama app\n  3. Run this script again.")
print(f"Ollama is running at {s['host']}")
if s["preferred_installed"]:
    sys.exit(f"{cfg['model']} is already installed. Nothing to do.")
print(f"Downloading {cfg['model']} (a few minutes)...")
last = ""
def show(p):
    global last
    line = f"{p['status']} {p['percent']}%" if p["percent"] is not None else p["status"]
    if line != last:
        print("\r" + line.ljust(60), end="", flush=True)
        last = line
cli.pull(cfg["model"], show)
print(f"\n{cfg['model']} is ready.")
