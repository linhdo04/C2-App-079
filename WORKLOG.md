# Worklog

## 2026-06-05 — Backend setup commit `71e00b4`

**What:** Logged the backend setup work from commit `71e00b4` (`setup: setup for backend`).

**Done:**
- Added initial FastAPI application entrypoint in `src/api/main.py`.
- Added `pyproject.toml` for Python packaging, runtime dependencies, dev dependencies, Ruff, mypy, pytest, and coverage configuration.
- Added `Makefile` targets for common backend workflows: `run`, `test`, `lint`, `format`, `format-check`, `typecheck`, and `check`.
- Added local `.pre-commit-config.yaml` hook to run `make check` before commits.
- Added placeholder pytest coverage in `tests/test_main.py` so the test command has an initial test file.
- Updated `README.md` with Team 079 project title, quick start commands, and backend setup instructions.
- Updated `.gitignore` to ignore local IDE folders `.idea/` and `.vscode/`.
- Marked `scripts/_pyrun.sh` as executable.

**Notes:**
- The FastAPI app currently exposes a simple root endpoint returning `"Hello, FastAPI with Uvicorn!"`.
- README and package description still contain placeholders that should be replaced once the project scope and team roles are finalized.
- Current tests are smoke/placeholders; add API-level tests once real endpoints are implemented.

## 2026-05-31 — Repo Initialization

**What:** Initialized project repository from the AI20K Build Cohort 2 starter template.

**Done:**
- Cloned starter-code-template and confirmed project structure is in place
- Verified AI logging hooks are configured for Claude Code, Cursor, Codex, Gemini CLI, Antigravity, and GitHub Copilot
- Confirmed `.env.example` is present; `.env` to be filled with `AI_LOG_SERVER` and `AI_LOG_API_KEY`
- Ran pre-push hook setup (Windows: `scripts\setup_hooks.ps1`)

**Next steps:**
- Decide on project idea and tech stack
- Assign initial tasks to team members
- Begin first feature implementation
