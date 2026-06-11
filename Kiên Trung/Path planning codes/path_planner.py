"""
Coverage Path Planners — RCPP and BECD
========================================
Phase 2: Coverage path planning over segmented farmland.

Two planners are provided for comparison:

  RotatingCalipersPlanner (RCPP)
    mask → farmland polygon → rotating calipers min-bbox → optimal sweep
    angle → single boustrophedon pass over the whole field.
    Best for: open farmland with sparse obstacles.

  BECDPlanner (Boustrophedon Exact Cell Decomposition)
    mask → column sweep → topology events (splits / merges) → cell
    decomposition → vertical boustrophedon per cell → greedy cell ordering.
    Best for: complex fields with many internal obstacles.

Class IDs (match train.py CLASS_NAMES):
    0 = background / farmland  ← coverage target
    1 = building               ← hard obstacle
    2 = woodland               ← hard obstacle (trees block low-altitude flight)
    3 = water                  ← hard obstacle
    4 = road                   ← passable, not target

Usage:
    python path_planner.py --mask mask.png --swath 40 --overlap 0.2 --out path.png
    python path_planner.py --mask mask.png --planner becd --json waypoints.json
"""

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import heapq

import cv2
import numpy as np


# ── Class IDs ─────────────────────────────────────────────────────────────────
FARMLAND = 0
BUILDING = 1
WOODLAND = 2
WATER    = 3
ROAD     = 4

HARD_OBSTACLES = (BUILDING, WOODLAND, WATER)

# BGR colours for visualisation
_COLOUR = {
    FARMLAND: (120, 210, 160),
    BUILDING: (80,   80, 200),
    WOODLAND: (40,  130,  40),
    WATER:    (200, 140,  50),
    ROAD:     (130, 130, 130),
}


@dataclass
class Waypoint:
    x:          float  # pixel column
    y:          float  # pixel row
    sweep_idx:  int    # sweep line index this point belongs to
    is_transit: bool = False  # True → repositioning move TO this point (not a coverage sweep)


class RotatingCalipersPlanner:
    """
    Coverage path planner that uses the Rotating Calipers algorithm (via
    cv2.minAreaRect) to find the minimum-area bounding rectangle of the
    farmland polygon.  The long axis of that rectangle gives the optimal
    sweep direction — sweeping parallel to the long axis minimises U-turns.

    Args:
        swath_width:   Camera footprint width in pixels.  Sweep lines are
                       spaced  swath_width * (1 - overlap)  pixels apart.
        overlap:       Fractional lateral overlap between adjacent sweeps.
        safety_margin: Pixels to inflate obstacle boundaries for clearance.
    """

    def __init__(
        self,
        swath_width:   int   = 40,
        overlap:       float = 0.20,
        safety_margin: int   = 10,
        astar_step:    int   = 8,
    ):
        if not (0.0 <= overlap < 1.0):
            raise ValueError("overlap must be in [0, 1)")
        self.swath_width   = swath_width
        self.step          = max(1, int(swath_width * (1.0 - overlap)))
        self.safety_margin = safety_margin
        self.astar_step    = astar_step
        self._last_angle   = 0.0   # stored after plan() for diagnostics

    # ── Public API ────────────────────────────────────────────────────────────

    def plan(self, mask: np.ndarray) -> List[Waypoint]:
        """
        Generate boustrophedon coverage waypoints from a segmentation mask.

        Every farmland region above a minimum area is covered (largest first),
        each with its own optimal sweep angle. Disconnected regions are
        stitched together with the same _line_free / _astar transit routing
        used for inter-segment gaps.

        Args:
            mask: H×W array of integer class IDs (0–4).

        Returns:
            Ordered list of Waypoint objects, or [] if no farmland found.
        """
        contours = self._farmland_contours(mask)
        if not contours:
            print("[RCPP] No farmland contour found.")
            return []

        obs_mask = self._obstacle_mask(mask)

        all_pts:        List[Waypoint] = []
        sweep_offset    = 0
        total_astar     = 0
        total_transits  = 0

        for i, contour in enumerate(contours):
            angle = self._sweep_angle(contour)
            if i == 0:
                self._last_angle = angle

            wps, n_astar, n_transits = self._boustrophedon(
                contour, obs_mask, angle, mask.shape[:2], sweep_offset)
            if not wps:
                continue

            sweep_offset    = wps[-1].sweep_idx + 1
            total_astar    += n_astar
            total_transits += n_transits

            if not all_pts:
                all_pts.extend(wps)
                continue

            # Stitch this region's first point to the previous region's last point
            total_transits += 1
            prev_x, prev_y = all_pts[-1].x, all_pts[-1].y
            next_x, next_y = wps[0].x, wps[0].y

            if not _line_free((prev_x, prev_y), (next_x, next_y), obs_mask):
                path = _astar((prev_x, prev_y), (next_x, next_y), obs_mask, step=self.astar_step)
                if path:
                    total_astar += 1
                    for tx, ty in path[1:-1]:
                        all_pts.append(Waypoint(float(tx), float(ty), wps[0].sweep_idx, True))

            wps[0].is_transit = True
            all_pts.extend(wps)

        if total_transits:
            print(f"[RCPP] A* rerouted {total_astar} / {total_transits} transit(s).")
        if len(contours) > 1:
            print(f"[RCPP] Covered {len(contours)} farmland region(s).")

        return all_pts

    def visualize(
        self,
        mask:      np.ndarray,
        waypoints: List[Waypoint],
        out_path:  str,
    ) -> np.ndarray:
        """
        Render the segmentation mask with the flight path overlaid.
        Saves to out_path and returns the BGR canvas.
        """
        h, w   = mask.shape[:2]
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        for cls_id, colour in _COLOUR.items():
            canvas[mask == cls_id] = colour

        if waypoints:
            pts = [(int(wp.x), int(wp.y)) for wp in waypoints]
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                colour = (0, 140, 255) if waypoints[i + 1].is_transit else (0, 255, 255)
                cv2.line(canvas, a, b, colour, 1, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(canvas, pt, 2, (0, 0, 255), -1)
            cv2.circle(canvas, pts[0],  6, (0, 255, 0),   -1)   # start  — green
            cv2.circle(canvas, pts[-1], 6, (255, 100, 0), -1)   # finish — orange

        cv2.imwrite(out_path, canvas)
        print(f"[RCPP] Visualisation saved → {out_path}")
        return canvas

    # ── Private helpers ───────────────────────────────────────────────────────

    def _farmland_contours(self, mask: np.ndarray) -> List[np.ndarray]:
        """
        Threshold class 0, apply morphological cleanup, return all external
        contours (= farmland regions) above a minimum area, largest first.
        Tiny slivers (smaller than ~2x2 swaths) are dropped as noise.
        """
        binary = (mask == FARMLAND).astype(np.uint8)
        k      = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, k)
        binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN,  k)

        contours, _ = cv2.findContours(
            binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        min_area = (self.swath_width * 2) ** 2
        contours = [c for c in contours if cv2.contourArea(c) >= min_area]
        contours.sort(key=cv2.contourArea, reverse=True)
        return contours

    def _obstacle_mask(self, mask: np.ndarray) -> np.ndarray:
        """Binary mask of hard obstacles, dilated by safety_margin pixels."""
        obs = np.isin(mask, HARD_OBSTACLES).astype(np.uint8)
        if self.safety_margin > 0:
            r      = self.safety_margin
            kernel = cv2.getStructuringElement(
                cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            obs = cv2.dilate(obs, kernel)
        return obs

    def _sweep_angle(self, contour: np.ndarray) -> float:
        """
        Rotating Calipers core step.

        cv2.minAreaRect internally runs the Rotating Calipers algorithm on
        the convex hull of the contour to find the minimum-area bounding
        rectangle.  We extract its angle and orient it so that the LONG axis
        of the rectangle aligns horizontally — sweeping horizontal lines then
        crosses the short dimension, giving the fewest U-turns.

        Returns angle in degrees (used as the rotation argument for
        cv2.getRotationMatrix2D).
        """
        _center, (w, h), angle = cv2.minAreaRect(contour)
        if h > w:       # long axis is more vertical → rotate an extra 90°
            angle += 90
        return float(angle)

    def _boustrophedon(
        self,
        field_contour: np.ndarray,
        obs_mask:      np.ndarray,
        angle_deg:     float,
        shape:         Tuple[int, int],
        sweep_offset:  int = 0,
    ) -> Tuple[List[Waypoint], int, int]:
        """
        1. Rotate everything so the field's long axis is horizontal.
        2. Sweep horizontal lines spaced `step` pixels apart.
        3. On each line find traversable segments (farmland AND not obstacle).
        4. Alternate left→right / right→left between lines (boustrophedon).
        5. Rotate waypoints back to the original image frame.
        6. Stitch every segment/sweep gap with A*-routed transit waypoints
           (same _line_free / _astar logic as BECDPlanner._cover_cells).

        Returns (waypoints, n_astar_reroutes, n_transits).
        """
        H, W   = shape
        cx, cy = W / 2.0, H / 2.0

        M     = cv2.getRotationMatrix2D((cx, cy),  angle_deg, 1.0)
        M_inv = cv2.getRotationMatrix2D((cx, cy), -angle_deg, 1.0)

        # Rotate contour into sweep frame and rasterise
        pts     = field_contour.reshape(-1, 2).astype(np.float32)
        pts_rot = cv2.transform(pts.reshape(1, -1, 2), M).reshape(-1, 2)

        field_rot = np.zeros((H, W), dtype=np.uint8)
        cv2.fillPoly(field_rot, [pts_rot.astype(np.int32)], 1)

        obs_rot = cv2.warpAffine(obs_mask, M, (W, H), flags=cv2.INTER_NEAREST)

        y_min = max(0,     int(pts_rot[:, 1].min()))
        y_max = min(H - 1, int(pts_rot[:, 1].max()))

        raw: List[Tuple[float, float, int]] = []   # (x, y, sweep_idx)
        left_to_right = True
        sweep_idx     = sweep_offset

        for y in range(y_min + self.step // 2, y_max, self.step):
            if not (0 <= y < H):
                continue

            traversable = field_rot[y].astype(bool) & ~obs_rot[y].astype(bool)
            xs          = np.where(traversable)[0]
            if len(xs) == 0:
                continue

            segments = _contiguous_segments(xs)

            if left_to_right:
                for x0, x1 in segments:
                    raw.append((float(x0), float(y), sweep_idx))
                    raw.append((float(x1), float(y), sweep_idx))
            else:
                for x0, x1 in reversed(segments):
                    raw.append((float(x1), float(y), sweep_idx))
                    raw.append((float(x0), float(y), sweep_idx))

            left_to_right = not left_to_right
            sweep_idx    += 1

        if not raw:
            return [], 0, 0

        # Rotate waypoints back to original frame
        src  = np.array([(x, y) for x, y, _ in raw],
                        dtype=np.float32).reshape(1, -1, 2)
        back = cv2.transform(src, M_inv).reshape(-1, 2)

        pts = [(float(back[i, 0]), float(back[i, 1]), raw[i][2])
               for i in range(len(raw))]

        # raw is built as alternating (coverage pair, gap, coverage pair, gap, ...)
        # i.e. transitions at even i (1->2, 3->4, ...) are gaps between segments
        # or sweep lines; transitions at odd i (0->1, 2->3, ...) are coverage runs.
        all_pts: List[Tuple[float, float, int, bool]] = [(*pts[0], False)]
        n_astar    = 0
        n_transits = 0

        for i in range(1, len(pts)):
            x, y, s = pts[i]
            is_gap  = (i % 2 == 0)
            if not is_gap:
                all_pts.append((x, y, s, False))
                continue

            n_transits += 1
            prev_x, prev_y = all_pts[-1][0], all_pts[-1][1]

            if _line_free((prev_x, prev_y), (x, y), obs_mask):
                all_pts.append((x, y, s, True))
            else:
                path = _astar((prev_x, prev_y), (x, y), obs_mask, step=self.astar_step)
                if path:
                    n_astar += 1
                    for tx, ty in path[1:]:
                        all_pts.append((tx, ty, s, True))
                else:
                    # A* hit limit — straight-line fallback
                    all_pts.append((x, y, s, True))

        wps = [Waypoint(x, y, s, t) for x, y, s, t in all_pts]
        return wps, n_astar, n_transits


# ── A* transit routing ────────────────────────────────────────────────────────

def _line_free(
    start_xy: Tuple[float, float],
    goal_xy:  Tuple[float, float],
    obs:      np.ndarray,
) -> bool:
    """Return True if the straight line between start and goal is obstacle-free."""
    x0, y0 = int(start_xy[0]), int(start_xy[1])
    x1, y1 = int(goal_xy[0]),  int(goal_xy[1])
    H, W   = obs.shape
    n      = max(abs(x1 - x0), abs(y1 - y0), 1)
    xs     = np.linspace(x0, x1, n + 1).astype(int).clip(0, W - 1)
    ys     = np.linspace(y0, y1, n + 1).astype(int).clip(0, H - 1)
    return not obs[ys, xs].any()


def _astar(
    start_xy: Tuple[float, float],
    goal_xy:  Tuple[float, float],
    obs:      np.ndarray,
    step:     int = 8,
    max_iter: int = 50_000,
) -> List[Tuple[float, float]]:
    """
    A* on a downsampled obstacle grid.

    Returns an ordered list of (x, y) pixel coords in the original image
    space (including start and goal).  Returns [] if the goal is unreachable
    or the node-expansion limit is hit (caller should fall back to straight line).

    Args:
        start_xy / goal_xy: pixel coords in original image space.
        obs:      H×W binary uint8 mask (1 = blocked).
        step:     Downsample factor — higher = faster but less precise routing.
        max_iter: Safety cap on node expansions to prevent runaway searches.
    """
    H, W = obs.shape

    # Max-pool downsample: a cell is blocked if ANY pixel inside it is blocked
    pad_h = (-H % step) % step
    pad_w = (-W % step) % step
    padded = np.pad(obs, ((0, pad_h), (0, pad_w)), constant_values=0)
    dH = padded.shape[0] // step
    dW = padded.shape[1] // step
    grid = padded.reshape(dH, step, dW, step).max(axis=(1, 3)).astype(bool)

    sx, sy = int(start_xy[0]) // step, int(start_xy[1]) // step
    gx, gy = int(goal_xy[0])  // step, int(goal_xy[1])  // step
    sx, sy = max(0, min(sx, dW - 1)), max(0, min(sy, dH - 1))
    gx, gy = max(0, min(gx, dW - 1)), max(0, min(gy, dH - 1))

    # Force start/goal cells open so A* can begin/end even inside a dilated margin
    grid[sy, sx] = False
    grid[gy, gx] = False

    if (sx, sy) == (gx, gy):
        return [start_xy, goal_xy]

    DIRS  = [(-1,0),(1,0),(0,-1),(0,1),(-1,-1),(-1,1),(1,-1),(1,1)]
    COSTS = [1.0,   1.0,  1.0,   1.0,  1.414,   1.414,  1.414,  1.414]

    g_score:   Dict[Tuple[int,int], float]                    = {(sx, sy): 0.0}
    came_from: Dict[Tuple[int,int], Optional[Tuple[int,int]]] = {(sx, sy): None}
    heap = [(np.hypot(sx - gx, sy - gy), 0.0, sx, sy)]
    iters = 0

    while heap:
        if iters >= max_iter:
            return []
        _, g, x, y = heapq.heappop(heap)
        iters += 1

        if g > g_score.get((x, y), float("inf")):
            continue

        if x == gx and y == gy:
            path: List[Tuple[int, int]] = []
            cur: Optional[Tuple[int, int]] = (gx, gy)
            while cur is not None:
                path.append(cur)
                cur = came_from[cur]
            path.reverse()
            result = [
                (float(px * step + step // 2), float(py * step + step // 2))
                for px, py in path
            ]
            result[0]  = start_xy
            result[-1] = goal_xy
            return result

        for (dx, dy), cost in zip(DIRS, COSTS):
            nx, ny = x + dx, y + dy
            if 0 <= nx < dW and 0 <= ny < dH and not grid[ny, nx]:
                ng = g + cost
                if ng < g_score.get((nx, ny), float("inf")):
                    g_score[(nx, ny)]   = ng
                    came_from[(nx, ny)] = (x, y)
                    heapq.heappush(heap, (ng + np.hypot(nx - gx, ny - gy), ng, nx, ny))

    return []


# ── BECD ──────────────────────────────────────────────────────────────────────

@dataclass
class _Cell:
    x_left:  int
    x_right: int
    y_top:   int
    y_bot:   int


class BECDPlanner:
    """
    Boustrophedon Exact Cell Decomposition coverage planner.

    Sweeps columns left-to-right to detect topology events (interval
    splits / merges), decomposes the traversable region into cells, then
    covers each cell with vertical boustrophedon sweeps.  Cells are
    stitched in greedy nearest-endpoint order.

    Args:
        swath_width:   Camera footprint width in pixels.
        overlap:       Fractional lateral overlap between adjacent sweeps.
        safety_margin: Pixels to inflate obstacle boundaries.
    """

    def __init__(
        self,
        swath_width:   int   = 40,
        overlap:       float = 0.20,
        safety_margin: int   = 10,
        astar_step:    int   = 8,
    ):
        if not 0.0 <= overlap < 1.0:
            raise ValueError("overlap must be in [0, 1)")
        self.swath_width   = swath_width
        self.step          = max(1, int(swath_width * (1.0 - overlap)))
        self.safety_margin = safety_margin
        self.astar_step    = astar_step
        self._cells: List[_Cell] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def plan(self, mask: np.ndarray) -> List[Waypoint]:
        obs  = self._obstacle_mask(mask)
        trav = ((mask == FARMLAND) & ~obs.astype(bool)).astype(np.uint8)
        if not trav.any():
            print("[BECD] No traversable area found.")
            return []
        cells = self._decompose(trav)
        self._cells = cells
        print(f"[BECD] Decomposed into {len(cells)} cell(s).")
        return self._cover_cells(cells, trav, obs)

    def visualize(
        self,
        mask:      np.ndarray,
        waypoints: List[Waypoint],
        out_path:  str,
    ) -> np.ndarray:
        h, w   = mask.shape[:2]
        canvas = np.zeros((h, w, 3), dtype=np.uint8)
        for cls_id, colour in _COLOUR.items():
            canvas[mask == cls_id] = colour

        for cell in self._cells:
            cv2.rectangle(
                canvas,
                (cell.x_left,  cell.y_top),
                (cell.x_right, cell.y_bot),
                (0, 220, 220), 1,
            )

        if waypoints:
            pts = [(int(wp.x), int(wp.y)) for wp in waypoints]
            for i, (a, b) in enumerate(zip(pts, pts[1:])):
                colour = (0, 140, 255) if waypoints[i + 1].is_transit else (0, 255, 255)
                cv2.line(canvas, a, b, colour, 1, cv2.LINE_AA)
            for pt in pts:
                cv2.circle(canvas, pt, 2, (0, 0, 255), -1)
            cv2.circle(canvas, pts[0],  6, (0, 255, 0),   -1)
            cv2.circle(canvas, pts[-1], 6, (255, 100, 0), -1)

        cv2.imwrite(out_path, canvas)
        print(f"[BECD] Visualisation saved → {out_path}")
        return canvas

    # ── Private ───────────────────────────────────────────────────────────────

    def _obstacle_mask(self, mask: np.ndarray) -> np.ndarray:
        obs = np.isin(mask, HARD_OBSTACLES).astype(np.uint8)
        if self.safety_margin > 0:
            r = self.safety_margin
            k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
            obs = cv2.dilate(obs, k)
        return obs

    @staticmethod
    def _col_intervals(col: np.ndarray) -> List[Tuple[int, int]]:
        ivs: List[Tuple[int, int]] = []
        y, n = 0, len(col)
        while y < n:
            if col[y]:
                start = y
                while y < n and col[y]:
                    y += 1
                ivs.append((start, y - 1))
            else:
                y += 1
        return ivs

    def _decompose(self, trav: np.ndarray) -> List[_Cell]:
        _, W = trav.shape
        cells: List[_Cell] = []
        active: Dict[Tuple[int, int], int] = {}  # interval → x_start

        for x in range(W):
            curr_ivs = self._col_intervals(trav[:, x])

            prev_to_curr: Dict[Tuple[int, int], List[Tuple[int, int]]] = {
                p: [c for c in curr_ivs if min(c[1], p[1]) >= max(c[0], p[0])]
                for p in active
            }
            curr_to_prev: Dict[Tuple[int, int], List[Tuple[int, int]]] = {
                c: [p for p in active if min(c[1], p[1]) >= max(c[0], p[0])]
                for c in curr_ivs
            }

            matched_prev: set = set()
            new_active: Dict[Tuple[int, int], int] = {}

            for c_iv in curr_ivs:
                prevs = curr_to_prev[c_iv]
                if not prevs:
                    new_active[c_iv] = x
                elif len(prevs) == 1:
                    p_iv = prevs[0]
                    if len(prev_to_curr[p_iv]) > 1:
                        # Split: close old cell, open a fresh one per new interval
                        if p_iv not in matched_prev:
                            cells.append(_Cell(active[p_iv], x - 1, p_iv[0], p_iv[1]))
                            matched_prev.add(p_iv)
                        new_active[c_iv] = x
                    else:
                        # Simple continuation
                        new_active[c_iv] = active[p_iv]
                        matched_prev.add(p_iv)
                else:
                    # Merge: close all contributing cells, open one new cell
                    for p_iv in prevs:
                        if p_iv not in matched_prev:
                            cells.append(_Cell(active[p_iv], x - 1, p_iv[0], p_iv[1]))
                            matched_prev.add(p_iv)
                    new_active[c_iv] = x

            for p_iv, x_start in active.items():
                if p_iv not in matched_prev:
                    cells.append(_Cell(x_start, x - 1, p_iv[0], p_iv[1]))

            active = new_active

        for iv, x_start in active.items():
            cells.append(_Cell(x_start, W - 1, iv[0], iv[1]))

        return [c for c in cells if c.x_right > c.x_left and c.y_bot > c.y_top]

    def _cover_cell(
        self,
        cell:         _Cell,
        trav:         np.ndarray,
        sweep_offset: int,
    ) -> List[Tuple[float, float, int]]:
        raw: List[Tuple[float, float, int]] = []
        top_to_bot = True
        sweep_idx  = sweep_offset

        for x in range(cell.x_left + self.step // 2, cell.x_right, self.step):
            x = min(x, trav.shape[1] - 1)
            col_slice = trav[cell.y_top : cell.y_bot + 1, x]
            ys_local  = np.where(col_slice)[0]
            if len(ys_local) == 0:
                continue
            ys       = ys_local + cell.y_top
            segments = _contiguous_segments(ys)

            if top_to_bot:
                for y0, y1 in segments:
                    raw.append((float(x), float(y0), sweep_idx))
                    raw.append((float(x), float(y1), sweep_idx))
            else:
                for y0, y1 in reversed(segments):
                    raw.append((float(x), float(y1), sweep_idx))
                    raw.append((float(x), float(y0), sweep_idx))

            top_to_bot = not top_to_bot
            sweep_idx += 1

        return raw

    def _cover_cells(
        self, cells: List[_Cell], trav: np.ndarray, obs: np.ndarray
    ) -> List[Waypoint]:
        sweep_offset = 0
        cell_segs: List[List[Tuple[float, float, int]]] = []
        for cell in cells:
            seg = self._cover_cell(cell, trav, sweep_offset)
            if seg:
                sweep_offset = seg[-1][2] + 1
            cell_segs.append(seg)

        non_empty = [(i, seg) for i, seg in enumerate(cell_segs) if seg]
        if not non_empty:
            return []

        # Greedy nearest-endpoint ordering across cells
        ordered = [non_empty[0]]
        remaining = list(non_empty[1:])
        while remaining:
            lx, ly = ordered[-1][1][-1][:2]
            best_j, best_d, flip = 0, float("inf"), False
            for j, (_, seg) in enumerate(remaining):
                ds = np.hypot(seg[0][0]  - lx, seg[0][1]  - ly)
                de = np.hypot(seg[-1][0] - lx, seg[-1][1] - ly)
                if ds < best_d:
                    best_d, best_j, flip = ds, j, False
                if de < best_d:
                    best_d, best_j, flip = de, j, True
            nxt_idx, nxt_seg = remaining.pop(best_j)
            if flip:
                nxt_seg = list(reversed(nxt_seg))
            ordered.append((nxt_idx, nxt_seg))

        # Stitch cells with A*-routed transitions
        all_pts: List[Tuple[float, float, int, bool]] = []
        n_astar = 0

        for i, (_, seg) in enumerate(ordered):
            if i == 0:
                for x, y, s in seg:
                    all_pts.append((x, y, s, False))
            else:
                prev_x, prev_y     = all_pts[-1][0], all_pts[-1][1]
                next_x, next_y, next_s = seg[0]

                if _line_free((prev_x, prev_y), (next_x, next_y), obs):
                    # Straight line is clear — direct transit
                    all_pts.append((next_x, next_y, next_s, True))
                else:
                    path = _astar(
                        (prev_x, prev_y), (next_x, next_y),
                        obs, step=self.astar_step,
                    )
                    if path:
                        n_astar += 1
                        # path[0] = prev point (already in all_pts), skip it
                        for tx, ty in path[1:]:
                            all_pts.append((tx, ty, next_s, True))
                    else:
                        # A* hit limit — straight-line fallback
                        all_pts.append((next_x, next_y, next_s, True))

                # Coverage waypoints for this cell (seg[0] already added above)
                for x, y, s in seg[1:]:
                    all_pts.append((x, y, s, False))

        if len(ordered) > 1:
            print(f"[BECD] A* rerouted {n_astar} / {len(ordered) - 1} inter-cell transition(s).")

        return [Waypoint(x, y, s, t) for x, y, s, t in all_pts]


# ── Utility ───────────────────────────────────────────────────────────────────

def _contiguous_segments(xs: np.ndarray) -> List[Tuple[int, int]]:
    """Split a sorted array of x-coords into (start, end) contiguous runs."""
    if len(xs) == 0:
        return []
    segs, start, prev = [], int(xs[0]), int(xs[0])
    for x in xs[1:]:
        x = int(x)
        if x > prev + 1:
            segs.append((start, prev))
            start = x
        prev = x
    segs.append((start, prev))
    return segs


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="Coverage path planners: RCPP and BECD")
    p.add_argument("--mask",    required=True,
                   help="Grayscale PNG segmentation mask (class IDs 0-4)")
    p.add_argument("--planner", choices=["rcpp", "becd"], default="rcpp",
                   help="Path planner to use (default: rcpp)")
    p.add_argument("--swath",   type=int,   default=40,
                   help="Swath width in pixels (default: 40)")
    p.add_argument("--overlap", type=float, default=0.20,
                   help="Lateral overlap fraction 0–1 (default: 0.20)")
    p.add_argument("--safety",  type=int,   default=10,
                   help="Obstacle safety margin in pixels (default: 10)")
    p.add_argument("--out",     default="flight_path.png",
                   help="Output visualisation image (default: flight_path.png)")
    p.add_argument("--json",    default=None,
                   help="Optional path to save waypoints as JSON")
    return p.parse_args()


def main():
    args = _parse_args()

    mask = cv2.imread(args.mask, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Cannot read mask: {args.mask}")

    if args.planner == "becd":
        planner   = BECDPlanner(args.swath, args.overlap, args.safety)
        waypoints = planner.plan(mask)
        tag = "BECD"
    else:
        planner   = RotatingCalipersPlanner(args.swath, args.overlap, args.safety)
        waypoints = planner.plan(mask)
        tag = "RCPP"
        print(f"[RCPP] Sweep angle  : {planner._last_angle:.1f}°")

    n_sweeps = (waypoints[-1].sweep_idx + 1) if waypoints else 0
    print(f"[{tag}] Sweep step   : {planner.step} px  "
          f"(swath={args.swath}, overlap={args.overlap})")
    print(f"[{tag}] Sweep lines  : {n_sweeps}")
    print(f"[{tag}] Total wpts   : {len(waypoints)}")

    planner.visualize(mask, waypoints, args.out)

    if args.json:
        Path(args.json).write_text(
            json.dumps([asdict(wp) for wp in waypoints], indent=2))
        print(f"[{tag}] Waypoints JSON → {args.json}")


if __name__ == "__main__":
    main()
