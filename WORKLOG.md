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
