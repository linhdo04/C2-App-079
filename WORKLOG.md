# WORKLOG — C2-App-079 AI Drone

---

## 2026-06-15 — Lovász-Softmax loss for road IoU, ignore training logs

### Context
Oversampling rare-class tiles (building, road) bumped val mIoU from 0.8236 →
0.8333, but road IoU barely moved (~0.59 → ~0.62) — tile-level oversampling
doesn't fix the per-pixel imbalance within those tiles, so pixel-averaged
losses (CE/Dice/Focal) still under-weight road.

### Changes made
- **`Kiên Trung/Segmentation models training codes/train.py`**:
  - Added `LovaszSoftmaxLoss` — Lovász-Softmax (Berman et al., 2018), a
    convex surrogate that directly optimizes per-class IoU. Known to help
    thin/rare classes (roads) more than pixel-averaged losses.
  - `CombinedLoss` now mixes CE (weighted) + Dice + Focal + Lovász, with
    weights 0.2 / 0.4 / 0.2 / 0.2 respectively.
- **`.gitignore`**: added `logs/` — per-run training JSON logs are
  regenerated each run and don't need to be tracked.

### Status
- Model checkpoint: `checkpoints/best_model.pth` — ResNet34, epoch 29, val mIoU **0.8333**
- Next: run training with the new loss and check whether road IoU improves
  beyond ~0.62.

## 2026-06-11 — A* transit routing (RCPP + BECD), multi-region RCPP coverage, enriched waypoint/mission JSON

### What was reviewed
Two issues were flagged against the BECD A* implementation:

1. **A* fallback ignores obstacles when max_iter is hit** — real but acceptable. The
   straight-line fallback only triggers when `_line_free` already confirmed the
   direct path is blocked AND A* exhausted its 50k-node budget — i.e. the two
   points are genuinely separated by a large obstacle with no nearby gap. The
   fallback is the only sane option (the alternative is leaving a coverage gap),
   and the point is tagged `is_transit=True` so it's visible in the simulation.

2. **A* forces start/goal cells open in the downsampled grid** — false positive.
   Start/goal points always come from the traversable mask (`trav`), so they can
   never be deep inside a hard obstacle; the forced-open only corrects for
   max-pool downsampling rounding at the safety-margin border.

Also reviewed: RCPP previously had **no obstacle-aware transit routing** — only
sweep segments were obstacle-free, but the straight-line moves between segments
and sweep lines could cross obstacles. And RCPP only covered the **single
largest** farmland contour, silently dropping all other disconnected farmland
patches.

### Changes made
- **`path_planner.py`**:
  - Added module-level `_line_free()` (Bresenham-style straight-line obstacle
    check) and `_astar()` (A* on a max-pool downsampled obstacle grid, 8-directional,
    `step=8`, `max_iter=50_000`).
  - **BECD**: `_cover_cells` now routes every inter-cell transition through
    `_line_free` → `_astar` → straight-line fallback. Prints
    `[BECD] A* rerouted N / M inter-cell transition(s).`
  - **RCPP**: `_boustrophedon` now stitches every segment/sweep gap with the same
    `_line_free`/`_astar`/fallback logic. Prints `[RCPP] A* rerouted N / M transit(s).`
  - **RCPP multi-region coverage**: `_largest_farmland_contour` →
    `_farmland_contours`, returning *all* farmland contours above a minimum area
    (~80x80px, filters noise), largest first. `plan()` sweeps each region at its
    own optimal angle and stitches regions together with A*. Prints
    `[RCPP] Covered N farmland region(s).`
  - Added `astar_step: int = 8` constructor arg to both planners.
- **`inference.py`**:
  - Added `enrich_waypoints()` — adds `heading`, `dist_from_prev_px`,
    `cumulative_dist_px` to each waypoint for web simulation playback.
  - Added `save_mission_json()` — exports `_mission_{suffix}.json` with image
    dimensions, planner name, total waypoints/distance, and coverage stats.
- **`cách chạy.txt`**: documented the new planner flags, output files, waypoint
  and mission JSON schemas, and the shared A* obstacle-avoidance behaviour.

### Test run
Re-ran segmentation + both planners on `M-33-32-B-b-4-4.tif` (9098x9621),
saved to `results/M-33-32-B-b-4-4/` (old single-region RCPP outputs removed):
- Coverage: background/farmland 78.1%, woodland 9.8%, water 10.6%, road 1.5%
- RCPP: 83,188 waypoints across multiple farmland regions
- BECD: 1431 cells, 16,986 waypoints, 329/757 inter-cell transitions A*-rerouted

### Status
- Model checkpoint: `checkpoints/best_model.pth` — ResNet34, epoch 25, val mIoU **0.8236**
- Next: integrate enriched waypoint/mission JSON into the web simulation
## 2026-06-09 — Persistent chat history and API routing

**Commit:** `889bb09` (`feat: add persistent chat history APIs`)

### Changes made

- Added persistent chat sessions with user-scoped ownership and soft deletion.
- Added APIs to create, list, search, retrieve, delete, and send messages to
  chats.
- Added search across both chat titles and message content.
- Stored user and assistant messages in `chat_histories`, linked through the
  new `chat_session_id` foreign key.
- Added migration `218a5abda747_add_chat_sessions.py` and applied it
  successfully.
- Reworked the Agent frontend into a responsive conversation workspace with:
  - New chat creation.
  - Chat history sidebar.
  - Chat search.
  - Chat deletion.
  - Full message history.
- Applied `API_PREFIX` through the parent FastAPI router.
- Updated refresh-cookie paths and the Swagger OAuth2 token URL to include the
  configured API prefix.
- Added public `GET /api/health`, excluded it from rate limiting, and removed
  the old root response returning `"Hello, FastAPI with Uvicorn!"`.
- Added a targeted pytest warning filter for the Python 3.14
  `_UnionGenericAlias` warning emitted by `google-genai`.
- Updated Agent, Auth, Health, and architecture documentation.

### Verification

- Backend format, lint, and mypy checks passed.
- Backend test suite passed: **109 tests**.
- Frontend format and lint checks passed.
- Next.js production build passed.
- Backend and frontend pre-commit hooks passed.

### Notes

- Chat history is persisted and displayed, but previous messages are not yet
  passed into the LangGraph state as LLM conversation context.
- Added SSE streaming for chat responses so the frontend renders Gemini output
  incrementally while persisting only the completed answer.
- Chat routes are URL-driven: `/agent` starts a new chat and
  `/agent/{chat_id}` opens existing history.
- Branch: `feat/chat-history-api`.

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

---

## 2026-06-08 — AI Agent implementation, routing, and review fixes

**Commits reviewed:** `083ec34`, `2a72634`, `5434e06`, `64417fc`,
`42d2eb9`, `3e0cd20`, `23d12d6`, `942b5b8`, `15a4f2d`

### Changes made

- Implemented the agricultural AI Agent using LangChain, LangGraph, and Gemini.
- Added the Agent graph, shared state, prompts, nodes, and tools for crop
  database queries, web search, weather forecasts, and crop data analysis.
- Added `POST /agent/ask` and connected the Agent router to FastAPI.
- Added intent routing and answer synthesis with graceful fallback behavior when
  tools or the LLM fail.
- Preserved the original user question across graph nodes instead of using
  intermediate node output as a new tool query.
- Improved keyword matching to avoid substring collisions and support common
  Vietnamese synonyms.
- Improved crop-data parsing for numbers before or after keywords, compact unit
  formats, decimal points, and decimal commas.
- Added tests for routing, tool execution, fallback behavior, keyword
  collisions, and numeric parsing.
- Added Agent documentation, architecture notes, ADRs, development guidance,
  and tool documentation.
- Added project-level `AGENTS.md`, Codex hooks, and reusable development
  workflow instructions.
- Reviewed earlier setup changes involving database sessions, rate limiting,
  dependencies, and pre-commit commands.

### Notes

- The Agent workflow at this stage was
  `route_intent -> execute_tools -> synthesize_answer`.
- Intent routing used deterministic keyword heuristics rather than LLM
  tool-calling.

---

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

---

## 2026-06-06 — Next.js frontend setup

**Commit:** `56db7af` (`setup: frontend nextjs`)

### Changes made

- Added the initial Next.js frontend with App Router, TypeScript, ESLint,
  Prettier, Tailwind/PostCSS configuration, and static assets.
- Added the initial application layout, global styles, and home page.
- Added frontend development documentation and package scripts.
- Added frontend-specific ignore and formatting configuration.
- Moved the existing backend project into `backend/`, establishing the current
  full-stack repository structure.
- Updated root documentation and pre-commit configuration for separate backend
  and frontend checks.

### Notes

- The initial frontend used pnpm workspace files; package management changed in
  later commits.

---

## 2026-06-05 — Segmentation and path-planning baseline

**Commit:** `0acb7d1`
(`feat(Kiên Trung): add segmentation, path planning, data, and results`)

### Changes made

- Added dataset loading and preprocessing scripts for map imagery.
- Added the initial semantic-segmentation training pipeline and notebook.
- Added model inference code for generating segmentation masks.
- Added the initial coverage path planner and waypoint generation.
- Added run instructions, experiment logs, generated masks, segmentation
  outputs, path visualizations, statistics, and waypoint results for the sample
  map.

### Notes

- This commit established the first computer-vision and path-planning baseline;
  BECD, transit tagging, A* obstacle avoidance, and enriched mission output were
  added in later commits.

---

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

---

## 2026-05-29 — Starter repository initialization

**Commit:** `42f8720`
(`chore: initialize repo from starter-code-template (cohort 2)`)

### Changes made

- Initialized the repository from the Cohort 2 starter template.
- Added the baseline README, environment template, Git ignore rules, worklog,
  and journal.
- Added AI activity logging hooks and configuration for Claude Code, Codex,
  Cursor, Gemini CLI, Antigravity, and GitHub Copilot.
- Added cross-platform hook setup and AI-log submission scripts.
- Added the initial `.ai-log` directory structure.

### Notes

- This commit established repository tooling and collaboration infrastructure;
  application code was added in later commits.
