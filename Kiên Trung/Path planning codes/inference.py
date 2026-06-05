"""
Inference Script — U-Net + ResNet34 Agricultural Segmentation
=============================================================
Phase 1 → Phase 2 bridge:
  Loads the trained model, segments a new drone image, saves the mask,
  then optionally feeds it into the RCPP path planner for flight waypoints.

Usage:
    # Segment only
    python inference.py --image field.jpg

    # Segment + plan flight path
    python inference.py --image field.jpg --plan --out_dir results/

    # Batch mode on a whole folder
    python inference.py --image_dir data/images/ --plan --out_dir results/

    # Custom checkpoint
    python inference.py --image field.jpg --checkpoint checkpoints/best_model.pth --plan
"""

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
import torch
import torch.nn.functional as F

try:
    import segmentation_models_pytorch as smp
    SMP_AVAILABLE = True
except ImportError:
    SMP_AVAILABLE = False

from path_planner import RotatingCalipersPlanner


# ── Constants — must match train.py ───────────────────────────────────────────
MEAN        = [0.3971, 0.4192, 0.3597]
STD         = [0.0967, 0.0832, 0.0708]
NUM_CLASSES = 5
TILE_SIZE   = 256
CLASS_NAMES = ["background", "building", "woodland", "water", "road"]

# BGR colours for segmentation visualisation
_PALETTE = {
    0: (120, 210, 160),   # farmland  — green
    1: (80,   80, 200),   # building  — red/blue
    2: (40,  130,  40),   # woodland  — dark green
    3: (200, 140,  50),   # water     — blue
    4: (130, 130, 130),   # road      — grey
}


# ── Model loading ─────────────────────────────────────────────────────────────

def load_model(checkpoint_path: str, device: torch.device) -> torch.nn.Module:
    if not SMP_AVAILABLE:
        raise ImportError("Install: pip install segmentation-models-pytorch")

    model = smp.Unet(
        encoder_name    = "resnet34",
        encoder_weights = None,       # weights come from the checkpoint
        in_channels     = 3,
        classes         = NUM_CLASSES,
    )
    ckpt  = torch.load(checkpoint_path, map_location=device)
    model.load_state_dict(ckpt["model"])
    model.eval().to(device)

    epoch     = ckpt.get("epoch",     "?")
    best_miou = ckpt.get("best_miou", float("nan"))
    print(f"[INF] Checkpoint  : {checkpoint_path}")
    print(f"[INF] Epoch       : {epoch}  |  Best val mIoU : {best_miou:.4f}")
    return model


# ── Pre / post processing ─────────────────────────────────────────────────────

def _normalize(img_rgb: np.ndarray) -> np.ndarray:
    """H×W×3 uint8 → float32, standardised with training stats."""
    x    = img_rgb.astype(np.float32) / 255.0
    mean = np.array(MEAN, dtype=np.float32)
    std  = np.array(STD,  dtype=np.float32)
    return (x - mean) / std


def mask_to_colour(mask: np.ndarray) -> np.ndarray:
    """H×W class-ID mask → H×W×3 BGR colour image."""
    canvas = np.zeros((*mask.shape, 3), dtype=np.uint8)
    for cls_id, colour in _PALETTE.items():
        canvas[mask == cls_id] = colour
    return canvas


# ── Tiled inference ───────────────────────────────────────────────────────────

@torch.no_grad()
def predict(
    model:  torch.nn.Module,
    image:  np.ndarray,        # H×W×3 RGB uint8
    device: torch.device,
    tile:   int = TILE_SIZE,
    stride: int = 192,         # overlap = tile - stride pixels per side
) -> np.ndarray:
    """
    Sliding-window inference on an arbitrary-size image.

    Softmax probabilities from overlapping tiles are averaged before
    the final argmax — this removes the seam artifacts that appear when
    tiles are just stitched at their hard boundary.

    Returns H×W uint8 mask of class IDs (0–4).
    """
    H, W   = image.shape[:2]
    logits = np.zeros((NUM_CLASSES, H, W), dtype=np.float32)
    counts = np.zeros((H, W),              dtype=np.float32)

    # Pad so the last tile always has full size
    pad_h  = (tile - H % tile) % tile if H >= tile else tile - H
    pad_w  = (tile - W % tile) % tile if W >= tile else tile - W
    padded = np.pad(image, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
    pH, pW = padded.shape[:2]

    for y in range(0, pH - tile + 1, stride):
        for x in range(0, pW - tile + 1, stride):
            patch = padded[y : y + tile, x : x + tile]
            norm  = _normalize(patch)
            t     = torch.from_numpy(norm.transpose(2, 0, 1)).unsqueeze(0).to(device)

            prob  = F.softmax(model(t), dim=1).squeeze(0).cpu().numpy()  # C×T×T

            # Only accumulate the portion that falls inside the original image
            y1, y2 = y, min(y + tile, H)
            x1, x2 = x, min(x + tile, W)
            logits[:, y1:y2, x1:x2] += prob[:, : y2 - y, : x2 - x]
            counts[    y1:y2, x1:x2] += 1.0

    logits /= np.maximum(counts, 1.0)
    return logits.argmax(axis=0).astype(np.uint8)


# ── Coverage statistics ───────────────────────────────────────────────────────

def coverage_stats(mask: np.ndarray) -> dict:
    total = mask.size
    return {
        name: {
            "pixels":  int((mask == i).sum()),
            "percent": round(int((mask == i).sum()) / total * 100, 2),
        }
        for i, name in enumerate(CLASS_NAMES)
    }


# ── Single-image pipeline ─────────────────────────────────────────────────────

def run_single(
    image_path: str,
    model:      torch.nn.Module,
    device:     torch.device,
    out_dir:    Path,
    *,
    plan:    bool  = False,
    tile:    int   = TILE_SIZE,
    stride:  int   = 192,
    swath:   int   = 40,
    overlap: float = 0.20,
    safety:  int   = 10,
):
    stem = Path(image_path).stem

    # 1 — Load image
    bgr = cv2.imread(image_path)
    if bgr is None:
        print(f"[WARN] Cannot read {image_path}, skipping.")
        return
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    H, W = rgb.shape[:2]
    print(f"\n[INF] ── {Path(image_path).name}  ({W}×{H}) ──────────────────")

    # 2 — Segment
    print("[INF] Segmenting...")
    mask = predict(model, rgb, device, tile=tile, stride=stride)

    mask_path = out_dir / f"{stem}_mask.png"
    seg_path  = out_dir / f"{stem}_seg.png"
    cv2.imwrite(str(mask_path), mask)
    cv2.imwrite(str(seg_path),  mask_to_colour(mask))
    print(f"[INF] Mask (class IDs)    → {mask_path}")
    print(f"[INF] Segmentation colour → {seg_path}")

    # 3 — Coverage stats
    stats      = coverage_stats(mask)
    stats_path = out_dir / f"{stem}_stats.json"
    stats_path.write_text(json.dumps(stats, indent=2))
    print(f"[INF] Coverage stats      → {stats_path}")
    for name, d in stats.items():
        bar = "█" * int(d["percent"] / 5)
        print(f"       {name:12s}: {d['percent']:5.1f}%  {bar}")

    # 4 — Path planning (optional)
    if not plan:
        return

    print("[INF] Running RCPP path planner...")
    planner   = RotatingCalipersPlanner(swath, overlap, safety)
    waypoints = planner.plan(mask)

    n_sweeps = (waypoints[-1].sweep_idx + 1) if waypoints else 0
    print(f"[INF] Sweep angle         : {planner._last_angle:.1f}°")
    print(f"[INF] Sweep lines         : {n_sweeps}")
    print(f"[INF] Total waypoints     : {len(waypoints)}")

    path_img  = out_dir / f"{stem}_path.png"
    wp_path   = out_dir / f"{stem}_waypoints.json"
    planner.visualize(mask, waypoints, str(path_img))
    wp_path.write_text(json.dumps([asdict(wp) for wp in waypoints], indent=2))
    print(f"[INF] Flight path vis     → {path_img}")
    print(f"[INF] Waypoints JSON      → {wp_path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def _parse_args():
    p = argparse.ArgumentParser(
        description="U-Net segmentation + RCPP path planning for agricultural drone")

    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--image",     help="Path to a single input image")
    src.add_argument("--image_dir", help="Directory of images (batch mode)")

    p.add_argument("--checkpoint", default="checkpoints/best_model.pth",
                   help="Model checkpoint  (default: checkpoints/best_model.pth)")
    p.add_argument("--out_dir",    default="results",
                   help="Output directory  (default: results/)")
    p.add_argument("--plan",       action="store_true",
                   help="Run RCPP path planner after segmentation")

    # Inference tuning
    p.add_argument("--tile",   type=int, default=TILE_SIZE,
                   help=f"Inference tile size px (default: {TILE_SIZE})")
    p.add_argument("--stride", type=int, default=192,
                   help="Sliding-window stride px (default: 192)")

    # Path planner tuning
    p.add_argument("--swath",   type=int,   default=40,
                   help="Swath width in px       (default: 40)")
    p.add_argument("--overlap", type=float, default=0.20,
                   help="Lateral overlap 0–1     (default: 0.20)")
    p.add_argument("--safety",  type=int,   default=10,
                   help="Obstacle safety margin  (default: 10)")

    p.add_argument("--cpu", action="store_true",
                   help="Force CPU (skip CUDA / MPS detection)")
    return p.parse_args()


def main():
    args = _parse_args()

    # Device
    if args.cpu:
        device = torch.device("cpu")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    else:
        device = torch.device("cpu")
    print(f"[INF] Device: {device}")

    model   = load_model(args.checkpoint, device)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.image:
        images = [args.image]
    else:
        exts   = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
        images = sorted(
            str(p) for p in Path(args.image_dir).iterdir()
            if p.suffix.lower() in exts
        )
        print(f"[INF] Found {len(images)} image(s) in {args.image_dir}")

    for img_path in images:
        run_single(
            img_path, model, device, out_dir,
            plan    = args.plan,
            tile    = args.tile,
            stride  = args.stride,
            swath   = args.swath,
            overlap = args.overlap,
            safety  = args.safety,
        )

    print(f"\n[INF] All done. Results → {out_dir.resolve()}")


if __name__ == "__main__":
    main()
