# StudiOS

A local-first virtual study desktop: courses, notes, planner, tasks, revision quizzes and a context-aware
AI assistant. It uses a frameless, locked OS-style shell and runs its AI locally through Ollama.

## Run it

1. Install Python 3.10+ (tick "Add python.exe to PATH" on Windows).
2. In this folder:
   ```
   python -m venv .venv
   .venv\Scripts\activate          (Mac/Linux: source .venv/bin/activate)
   pip install -r requirements.txt
   python main.py
   ```
3. First launch opens full-screen setup for your profile and local password. StudiOS then opens on its lock screen.
   At each launch, StudiOS checks for the local Ollama runtime, starts it without opening a terminal, and
   downloads `qwen2.5:1.5b` itself if needed. If Ollama is not installed, an in-app setup notice appears;
   use **System Setup** to open the official installer page. The model is downloaded once and reused.
4. Open **Browser** or choose **Open in StudiOS** on a course to browse course sites inside the app.
5. `python scripts/selftest.py` checks the database, quiz flow and Ollama error handling without requiring
   a running model. `python -m unittest test_os test_ai test_ui` runs the focused suite, and
   `python test_ram_usage.py` reports app and Ollama memory when detectable.

Choosing **Reset everything** erases the local StudiOS profile and data, then shuts down the app.
The next launch starts the first-run setup again; a previously downloaded Ollama model is retained.

## Structure

```
main.py                     entry point
StudiOS/
  config.py                 defaults: model, modules, exams, data folder (edit here first)
  runtime.py                AppContext (shared state), background Worker, study timer
  app.py                    full-screen startup and first-run setup
  core/                     no UI code
    db.py                   SQLite document store + backup/restore
    ollama.py               Ollama client: status, pull, chat stream, JSON mode
    backend.py              local Ollama discovery, service start and automatic model download
    context.py              builds the AI system prompt from course + subject + notes
    quiz.py                 quiz prompts and validation
    stats.py                progress numbers
    favicons.py             course logos (cached)
  ui/
    theme.py                colours + stylesheet
    widgets.py              Panel, BarChart, icons, helpers
    main_window.py          lock screen, OS panel, dock and lazy page switching
    pages/                  one file per module (dashboard, courses, notes, assistant,
                            planner, revision, tasks, progress, browser, system setup, settings, wizard)
scripts/                    setup_ollama.py, selftest.py
assets/                     logos
```

Data lives in `~/.studios/studios.db` (override with the `STUDIOS_HOME` environment variable).

## Add a module

1. Create `StudiOS/ui/pages/mypage.py` with a class extending `Page` or `DynamicPage` (see `tasks.py`).
2. Add one line to `PAGES` in `StudiOS/ui/pages/__init__.py` and to `MODULES` in `config.py`.
3. Add its icon path to `ICON_PATHS` in `ui/widgets.py`.

Pages read and write data with `self.db` (`add`, `list`, `update`, `remove`), call the AI with
`self.ctx.run(...)` so the window never freezes, and switch pages with `self.ctx.go("notes", note_id=...)`.
To add a new kind of record, just use a new name in `COLLECTIONS` in `core/db.py`.
to install requirements : pip install -r requirements.txt