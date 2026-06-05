"""
LandCover.ai — Agriculture-Focused Preprocessing Pipeline
==========================================================
Project: AI Trợ Lý Drone Tự Hành Cho Khảo Sát & Giám Sát
Model  : U-Net + ResNet34 backbone
Focus  : Agriculture (background class = farmland in rural aerial imagery)

Dataset structure expected:
    data/
    ├── images/          ← original large orthophotos (.tif or .jpg)
    ├── masks/           ← corresponding annotation masks (.tif or .png)
    ├── train.txt        ← provided by dataset
    ├── val.txt
    └── test.txt

Output structure:
    data/processed/
    ├── images/          ← 256×256 tiles
    ├── masks/           ← 256×256 label tiles
    ├── train.txt        ← filtered tile lists
    ├── val.txt
    └── test.txt
"""

import os
import cv2
import numpy as np
from PIL import Image
from pathlib import Path
import shutil
import json
from collections import defaultdict
import random
import warnings
warnings.filterwarnings("ignore")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
RAW_IMAGE_DIR   = Path("data/images")
RAW_MASK_DIR    = Path("data/masks")
OUTPUT_DIR      = Path("data/processed")
TILE_SIZE       = 256
STRIDE          = 256          # no overlap; use 256 for overlap-based augmentation
MIN_AGRI_RATIO  = 0.10         # discard tiles with less than 10% agriculture pixels
RANDOM_SEED     = 42

# LandCover.ai label mapping
# Mask pixel values → class index
LABEL_MAP = {
    0: "background",   # ← AGRICULTURE / farmland (our primary target)
    1: "building",
    2: "woodland",
    3: "water",
    4: "road",
}

# For display / reporting
CLASS_COLORS = {
    0: (210, 180, 140),   # tan — farmland
    1: (128, 128, 128),   # grey — building
    2: (34,  139,  34),   # green — woodland
    3: (30,  144, 255),   # blue — water
    4: (255, 165,   0),   # orange — road
}

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)


# ─────────────────────────────────────────────
# STEP 1: TILE SPLITTER
# ─────────────────────────────────────────────
def split_image_and_mask(image_path: Path, mask_path: Path,
                          out_img_dir: Path, out_mask_dir: Path,
                          tile_size: int = TILE_SIZE,
                          stride: int = STRIDE) -> list[str]:
    """
    Splits one orthophoto + mask into non-overlapping tiles of the given size.
    Returns list of saved tile stem names.
    """
    img  = cv2.imread(str(image_path), cv2.IMREAD_COLOR)   # BGR
    mask = cv2.imread(str(mask_path),  cv2.IMREAD_GRAYSCALE)

    if img is None or mask is None:
        print(f"  [WARN] Could not read {image_path.name}, skipping.")
        return []

    h, w = img.shape[:2]
    saved = []

    tile_idx = 0
    for y in range(0, h - tile_size + 1, stride):
        for x in range(0, w - tile_size + 1, stride):
            img_tile  = img [y:y+tile_size, x:x+tile_size]
            mask_tile = mask[y:y+tile_size, x:x+tile_size]

            stem = f"{image_path.stem}_{tile_idx:04d}"
            cv2.imwrite(str(out_img_dir  / f"{stem}.jpg"),  img_tile,
                        [cv2.IMWRITE_JPEG_QUALITY, 95])
            cv2.imwrite(str(out_mask_dir / f"{stem}.png"),  mask_tile)

            saved.append(stem)
            tile_idx += 1

    return saved


def tile_all_images(raw_img_dir: Path, raw_mask_dir: Path,
                    out_dir: Path) -> list[str]:
    """Tile every image-mask pair in the raw directories."""
    out_img_dir  = out_dir / "images"
    out_mask_dir = out_dir / "masks"
    out_img_dir.mkdir(parents=True, exist_ok=True)
    out_mask_dir.mkdir(parents=True, exist_ok=True)

    image_paths = sorted(list(raw_img_dir.glob("*.tif")) +
                         list(raw_img_dir.glob("*.jpg")) +
                         list(raw_img_dir.glob("*.png")))

    all_tiles = []
    for img_path in image_paths:
        # Find matching mask (same stem, any extension)
        mask_candidates = list(raw_mask_dir.glob(f"{img_path.stem}.*"))
        if not mask_candidates:
            print(f"  [WARN] No mask found for {img_path.name}")
            continue
        mask_path = mask_candidates[0]

        print(f"  Tiling {img_path.name} ...")
        tiles = split_image_and_mask(img_path, mask_path,
                                      out_img_dir, out_mask_dir)
        all_tiles.extend(tiles)
        print(f"    → {len(tiles)} tiles generated")

    print(f"\nTotal tiles: {len(all_tiles)}")
    return all_tiles


# ─────────────────────────────────────────────
# STEP 2: AGRICULTURE FILTER
# ─────────────────────────────────────────────
def compute_class_ratios(mask_path: Path) -> dict:
    """Returns per-class pixel ratio for one mask tile."""
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    total = mask.size
    ratios = {}
    for label_id in LABEL_MAP:
        ratios[label_id] = float(np.sum(mask == label_id)) / total
    return ratios


def filter_tiles_by_agriculture(tile_stems: list[str],
                                 out_dir: Path,
                                 min_agri_ratio: float = MIN_AGRI_RATIO,
                                 ) -> tuple[list[str], dict]:
    """
    Keep only tiles that have >= min_agri_ratio of background (farmland).
    Also returns per-tile stats for EDA.
    """
    mask_dir = out_dir / "masks"
    kept  = []
    stats = {}

    for stem in tile_stems:
        mask_path = mask_dir / f"{stem}.png"
        if not mask_path.exists():
            continue
        ratios = compute_class_ratios(mask_path)
        agri_ratio = ratios[0]   # class 0 = background = farmland

        stats[stem] = ratios
        if agri_ratio >= min_agri_ratio:
            kept.append(stem)

    dropped = len(tile_stems) - len(kept)
    print(f"Agriculture filter: kept {len(kept)}/{len(tile_stems)} tiles "
          f"(dropped {dropped} with <{min_agri_ratio*100:.0f}% farmland)")
    return kept, stats


# ─────────────────────────────────────────────
# STEP 3: SYNC WITH OFFICIAL SPLITS
# ─────────────────────────────────────────────
def load_official_split(txt_path: Path) -> set[str]:
    """Load official train/val/test tile list from dataset-provided .txt"""
    if not txt_path.exists():
        return set()
    with open(txt_path) as f:
        return {line.strip() for line in f if line.strip()}


def build_splits(filtered_tiles: list[str],
                 raw_dir: Path,
                 out_dir: Path) -> dict[str, list[str]]:
    """
    If official split files exist, use them filtered by our agriculture mask.
    Otherwise, do an 80/10/10 random split.
    """
    train_official = load_official_split(raw_dir / "train.txt")
    val_official   = load_official_split(raw_dir / "val.txt")
    test_official  = load_official_split(raw_dir / "test.txt")

    filtered_set = set(filtered_tiles)

    train_intersect = sorted(filtered_set & train_official)
    val_intersect   = sorted(filtered_set & val_official)
    test_intersect  = sorted(filtered_set & test_official)
    official_valid  = bool(train_intersect and val_intersect and test_intersect)

    if official_valid:
        splits = {
            "train": train_intersect,
            "val":   val_intersect,
            "test":  test_intersect,
        }
        unassigned = filtered_set - train_official - val_official - test_official
        splits["train"].extend(sorted(unassigned))
        print("Using official train/val/test splits (intersected with agriculture filter)")
    else:
        # Official splits exist but stems don't match (e.g. different tile size/naming) → random 70/15/15
        shuffled = filtered_tiles.copy()
        random.shuffle(shuffled)
        n = len(shuffled)
        n_train = int(n * 0.70)
        n_val   = int(n * 0.15)
        splits = {
            "train": shuffled[:n_train],
            "val":   shuffled[n_train:n_train + n_val],
            "test":  shuffled[n_train + n_val:],
        }
        print("Official splits don't match tile names — using random 70/15/15 split")

    for split, tiles in splits.items():
        print(f"  {split:5s}: {len(tiles)} tiles")
        out_path = out_dir / f"{split}.txt"
        with open(out_path, "w") as f:
            f.write("\n".join(tiles))

    return splits


# ─────────────────────────────────────────────
# STEP 4: DATASET STATS & EDA SUMMARY
# ─────────────────────────────────────────────
def compute_mean_std(image_dir: Path, tile_list: list[str],
                     sample_size: int = 500) -> tuple:
    """
    Compute per-channel mean and std on a sample of training tiles.
    Used for normalization in the DataLoader.
    """
    sample = random.sample(tile_list, min(sample_size, len(tile_list)))
    means, stds = [], []

    for stem in sample:
        path = image_dir / f"{stem}.jpg"
        if not path.exists():
            continue
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        means.append(img.reshape(-1, 3).mean(axis=0))
        stds.append(img.reshape(-1, 3).std(axis=0))

    mean = np.array(means).mean(axis=0).tolist()
    std  = np.array(stds ).mean(axis=0).tolist()
    return mean, std


def generate_eda_report(tile_stats: dict, splits: dict, out_dir: Path,
                         mean: list, std: list):
    """Save a JSON summary of dataset statistics."""
    # Aggregate class distribution across train set
    class_totals = defaultdict(float)
    for stem in splits.get("train", []):
        if stem in tile_stats:
            for cls_id, ratio in tile_stats[stem].items():
                class_totals[cls_id] += ratio

    n_train = max(len(splits["train"]), 1)
    class_dist = {
        LABEL_MAP[k]: round(v / n_train * 100, 2)
        for k, v in class_totals.items()
    }

    report = {
        "split_sizes": {k: len(v) for k, v in splits.items()},
        "tile_size": TILE_SIZE,
        "min_agriculture_ratio": MIN_AGRI_RATIO,
        "normalization": {
            "mean": [round(x, 4) for x in mean],
            "std":  [round(x, 4) for x in std],
        },
        "class_distribution_train_pct": class_dist,
        "note": (
            "Class 0 (background) = farmland/agriculture. "
            "Tiles with <10% farmland pixels were excluded."
        ),
    }

    report_path = out_dir / "dataset_stats.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nEDA report saved → {report_path}")
    print(json.dumps(report, indent=2))


# ─────────────────────────────────────────────
# STEP 5: PYTORCH DATASET CLASS
# ─────────────────────────────────────────────
DATASET_CLASS_CODE = '''"""
LandCoverAgriDataset — PyTorch Dataset for U-Net + ResNet34 training
=====================================================================
Drop this file next to preprocess.py and import in your training script.

Usage:
    from dataset import LandCoverAgriDataset, get_transforms
    train_ds = LandCoverAgriDataset("data/processed", split="train",
                                     transform=get_transforms("train"))
"""

import cv2
import numpy as np
from pathlib import Path
from torch.utils.data import Dataset
import albumentations as A
from albumentations.pytorch import ToTensorV2

# ── Normalization stats (update with values from dataset_stats.json) ──
MEAN = [0.485, 0.456, 0.406]   # fallback: ImageNet mean
STD  = [0.229, 0.224, 0.225]   # fallback: ImageNet std


class LandCoverAgriDataset(Dataset):
    """
    Loads 512×512 image + mask tiles.
    Label 0 = farmland (agriculture) — PRIMARY class for drone mission.
    Labels 1-4 = building, woodland, water, road (obstacles / context).
    """

    NUM_CLASSES = 5

    def __init__(self, root: str, split: str = "train", transform=None):
        self.root      = Path(root)
        self.transform = transform
        self.img_dir   = self.root / "images"
        self.mask_dir  = self.root / "masks"

        split_file = self.root / f"{split}.txt"
        with open(split_file) as f:
            self.stems = [l.strip() for l in f if l.strip()]

    def __len__(self):
        return len(self.stems)

    def __getitem__(self, idx):
        stem = self.stems[idx]
        img  = cv2.imread(str(self.img_dir  / f"{stem}.jpg"), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(self.mask_dir / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        if self.transform:
            augmented = self.transform(image=img, mask=mask)
            img  = augmented["image"]
            mask = augmented["mask"].long()

        return img, mask


def get_transforms(split: str, mean=MEAN, std=STD):
    """
    Returns albumentations transform pipeline.
    Agriculture-aware augmentations:
    - RandomBrightnessContrast  → simulate different lighting / seasons
    - HueSaturationValue        → simulate different crop colors
    - GridDistortion            → simulate UAV camera lens distortion
    - HorizontalFlip / RandomRotate90 → field orientation invariance
    """
    if split == "train":
        return A.Compose([
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.3),
            A.RandomRotate90(p=0.5),
            A.RandomBrightnessContrast(
                brightness_limit=0.2,
                contrast_limit=0.2, p=0.5),
            A.HueSaturationValue(
                hue_shift_limit=10,
                sat_shift_limit=20,
                val_shift_limit=10, p=0.4),
            A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.3),
            A.GaussianBlur(blur_limit=(3, 5), p=0.2),
            A.Normalize(mean=mean, std=std),
            ToTensorV2(),
        ])
    else:
        # val / test — only normalize, no augmentation
        return A.Compose([
            A.Normalize(mean=mean, std=std),
            ToTensorV2(),
        ])
'''


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    print("=" * 60)
    print("LandCover.ai Agriculture Preprocessing Pipeline")
    print("=" * 60)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Tile ──────────────────────────────────────────
    print(f"\n[1/5] Splitting orthophotos into {TILE_SIZE}×{TILE_SIZE} tiles...")
    if not RAW_IMAGE_DIR.exists():
        print(f"  [DEMO MODE] {RAW_IMAGE_DIR} not found.")
        print("  In real usage: place dataset images in data/images/")
        print("                 and masks in data/masks/")
        all_tiles = [f"demo_tile_{i:04d}" for i in range(200)]
        print(f"  Simulating {len(all_tiles)} tiles for demo.")
    else:
        all_tiles = tile_all_images(RAW_IMAGE_DIR, RAW_MASK_DIR, OUTPUT_DIR)

    # ── Step 2: Agriculture filter ────────────────────────────
    print("\n[2/5] Filtering tiles by agriculture coverage...")
    mask_dir = OUTPUT_DIR / "masks"
    if mask_dir.exists() and any(mask_dir.iterdir()):
        filtered_tiles, tile_stats = filter_tiles_by_agriculture(
            all_tiles, OUTPUT_DIR, MIN_AGRI_RATIO)
    else:
        # Demo mode: simulate stats
        print("  [DEMO MODE] Simulating agriculture filter...")
        filtered_tiles = all_tiles[:160]
        tile_stats = {
            stem: {0: 0.55, 1: 0.05, 2: 0.20, 3: 0.10, 4: 0.10}
            for stem in filtered_tiles
        }
        print(f"  Kept {len(filtered_tiles)}/{len(all_tiles)} tiles")

    # ── Step 3: Build splits ──────────────────────────────────
    print("\n[3/5] Building train/val/test splits...")
    splits = build_splits(filtered_tiles, Path("data"), OUTPUT_DIR)

    # ── Step 4: Compute normalization stats ───────────────────
    print("\n[4/5] Computing normalization mean/std from training tiles...")
    img_dir = OUTPUT_DIR / "images"
    if img_dir.exists() and any(img_dir.iterdir()):
        mean, std = compute_mean_std(img_dir, splits["train"])
    else:
        # Fallback to ImageNet stats (safe default for pretrained ResNet34)
        mean = [0.485, 0.456, 0.406]
        std  = [0.229, 0.224, 0.225]
        print("  [DEMO MODE] Using ImageNet normalization stats as fallback.")

    print(f"  Mean (R,G,B): {[round(x,4) for x in mean]}")
    print(f"  Std  (R,G,B): {[round(x,4) for x in std]}")

    # ── Step 5: EDA report ────────────────────────────────────
    print("\n[5/5] Generating EDA report...")
    generate_eda_report(tile_stats, splits, OUTPUT_DIR, mean, std)

    # ── Write Dataset class ───────────────────────────────────
    dataset_file = OUTPUT_DIR.parent / "dataset.py"
    with open(dataset_file, "w") as f:
        f.write(DATASET_CLASS_CODE)
    print(f"\nPyTorch Dataset class saved → {dataset_file}")

    print("\n" + "=" * 60)
    print("Preprocessing complete.")
    print(f"Processed data → {OUTPUT_DIR.resolve()}")
    print("Next step: run   python train.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
