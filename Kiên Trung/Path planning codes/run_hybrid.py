"""
Standalone hybrid-planner runner (BECD cells + RCPP per-cell angle).

Runs HybridPlanner directly on a saved segmentation mask (class IDs 0-4) and
writes the same artefact set inference.py produces for the other planners:

    <stem>_path_hybrid.png       flight-path visualisation
    <stem>_waypoints_hybrid.json enriched waypoints (heading + distances)
    <stem>_mission_hybrid.json   mission summary

Usage:
    python run_hybrid.py --mask results/<stem>/<stem>_mask.png --out_dir results/<stem>
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

from path_planner import HybridPlanner, FARMLAND, HARD_OBSTACLES

CLASS_NAMES = ["background", "building", "woodland", "water", "road"]


def enrich_waypoints(waypoints) -> list:
    """Add heading, dist_from_prev_px, cumulative_dist_px (matches inference.py)."""
    result, cum = [], 0.0
    for i, wp in enumerate(waypoints):
        d = asdict(wp)
        if i == 0:
            heading = dist_prev = 0.0
        else:
            prev      = waypoints[i - 1]
            dx, dy    = wp.x - prev.x, wp.y - prev.y
            dist_prev = float(np.hypot(dx, dy))
            heading   = float(np.degrees(np.arctan2(dy, dx)) % 360)
        cum += dist_prev
        d["heading"]            = round(heading,   2)
        d["dist_from_prev_px"]  = round(dist_prev, 2)
        d["cumulative_dist_px"] = round(cum,       2)
        result.append(d)
    return result


def coverage_stats(mask: np.ndarray) -> dict:
    total = mask.size
    return {
        name: {
            "pixels":  int((mask == i).sum()),
            "percent": round(int((mask == i).sum()) / total * 100, 2),
        }
        for i, name in enumerate(CLASS_NAMES)
    }


def main():
    ap = argparse.ArgumentParser(description="Run the hybrid BECD+RCPP planner on a mask")
    ap.add_argument("--mask", required=True, help="Grayscale class-ID mask PNG")
    ap.add_argument("--out_dir", default=None, help="Output dir (default: mask's folder)")
    ap.add_argument("--swath",   type=int,   default=40)
    ap.add_argument("--overlap", type=float, default=0.20)
    ap.add_argument("--safety",  type=int,   default=10)
    args = ap.parse_args()

    mask = cv2.imread(args.mask, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Cannot read mask: {args.mask}")
    H, W = mask.shape[:2]
    stem = Path(args.mask).stem.replace("_mask", "")
    out_dir = Path(args.out_dir) if args.out_dir else Path(args.mask).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[RUN] Mask {stem}  ({W}x{H})")
    planner   = HybridPlanner(args.swath, args.overlap, args.safety)
    waypoints = planner.plan(mask)
    n_sweeps  = (waypoints[-1].sweep_idx + 1) if waypoints else 0
    enriched  = enrich_waypoints(waypoints)
    total_dist = sum(wp["dist_from_prev_px"] for wp in enriched)

    path_img  = out_dir / f"{stem}_path_hybrid.png"
    wp_json   = out_dir / f"{stem}_waypoints_hybrid.json"
    mis_json  = out_dir / f"{stem}_mission_hybrid.json"

    planner.visualize(mask, waypoints, str(path_img))
    wp_json.write_text(json.dumps(enriched, indent=2))
    mis_json.write_text(json.dumps({
        "image":           {"width": W, "height": H},
        "planner":         "hybrid",
        "cells":           len(planner._cells),
        "sweep_lines":     n_sweeps,
        "total_waypoints": len(waypoints),
        "total_dist_px":   round(total_dist, 2),
        "coverage":        coverage_stats(mask),
    }, indent=2))

    print(f"[RUN] cells={len(planner._cells)}  sweeps={n_sweeps}  "
          f"waypoints={len(waypoints)}  total_dist={total_dist:.0f}px")
    print(f"[RUN] Path vis   -> {path_img}")
    print(f"[RUN] Waypoints  -> {wp_json}")
    print(f"[RUN] Mission    -> {mis_json}")


if __name__ == "__main__":
    main()
