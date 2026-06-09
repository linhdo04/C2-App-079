# WORKLOG — C2-App-079 AI Drone

---

## 2026-06-09 — Bug fixes & transit waypoint tagging

### What was reviewed
Three issues were flagged against the path planning code:

1. **Potential index error in `BECDPlanner._decompose` at x=0** — FALSE POSITIVE.
   At `x = 0`, `active` is always empty so the split/merge branches that use `x - 1` are unreachable. No fix needed.

2. **Architecture mismatch: ResNet34 vs ResNet50** — REAL BUG.
   `train.py` had been changed to `resnet50` in a previous session (attempt to improve accuracy). The existing checkpoint at `checkpoints/best_model.pth` was trained on ResNet34 (confirmed by inspecting state dict key count: 278 keys = ResNet34, vs the newer training-codes checkpoint with 380 keys = ResNet50). `inference.py` correctly uses `resnet34` — the bug was in `train.py`.

3. **Greedy inter-cell path discontinuity in BECD** — REAL but not a crash bug.
   `BECDPlanner._cover_cells` concatenates cell waypoints without transition routing. If two cells are non-adjacent, the drone would fly a straight line through obstacles between them. Fixed by tagging rather than rerouting (A* transitions deferred to next phase).

### Changes made
- **`train.py`**: Reverted `encoder_name` → `resnet34`, updated docstring to match.
- **`path_planner.py`**:
  - Added `is_transit: bool = False` field to `Waypoint` dataclass.
  - RCPP: first waypoint of each new sweep line tagged `is_transit=True`.
  - BECD: first waypoint of each non-first cell tagged `is_transit=True`.
  - Both `visualize()` methods: transit lines render in orange, coverage sweeps in cyan.
  - Waypoints JSON now exports `{x, y, sweep_idx, is_transit}`.

### Status
- PR #13 updated: https://github.com/AI20K-Build-Cohort-2/C2-App-079/pull/13
- Model checkpoint: `checkpoints/best_model.pth` — ResNet34, epoch 22, val mIoU **0.8233**
- Next: simulation-level obstacle avoidance (A* inter-cell transitions) for BECD
# Worklog

## 2026-06-07 — Added migrations, DB, Redis, error handling, rate limiting, logging

**What:** Implemented database migrations, Postgres integration, Redis cache, and API middlewares.

**Done:**

- Added Alembic migration files and updated migration config under `backend/migrations/` and `alembic.ini`.
- Added Postgres integration in `src/infrastructure/database/postgres.py` and configured DB startup/shutdown events.
- Added Redis cache integration in `src/infrastructure/cache/redis.py` with startup/shutdown hooks.
- Registered error handling middleware in `src/api/middlewares/error_handling.py`.
- Registered rate limiting middleware in `src/api/middlewares/rate_limiting.py`.
- Added request/response logging middleware and centralized logging configuration in `src/api/middlewares/logging.py` and `src/core/logging.py`.
- Updated `src/api/main.py` to register the above middlewares and to connect/disconnect DB and Redis on startup/shutdown.

**Notes:**

- Alembic migrations can be applied with:

  ```
  cd backend
  make db-upgrade
  ```

- Ensure environment variables for Postgres and Redis are set before running the app.

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
