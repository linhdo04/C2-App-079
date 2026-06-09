"""
Training Script — U-Net + ResNet34 for Agricultural Land Segmentation
======================================================================
Dataset : LandCover.ai (preprocessed by preprocess.py)
Model   : U-Net with ResNet50 encoder (pretrained on ImageNet)
Loss    : CE (weighted) + DiceLoss + FocalLoss (handles class imbalance)
Metrics : IoU per class + mean IoU

Your dataset stats (computed from data/processed/train/images/):
    Mean : [0.3724, 0.3983, 0.3451]
    Std  : [0.1089, 0.0978, 0.0786]
    Class distribution (train):
        background (farmland) : 72.33%
        woodland              : 20.58%
        water                 :  4.13%
        road                  :  1.86%
        building              :  1.10%

Run:
    python train.py
    python train.py --epochs 50 --batch_size 8 --lr 0.0001
"""

import os
import json
import random
import argparse
import numpy as np
from pathlib import Path
from datetime import datetime

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader, random_split
import cv2
import albumentations as A
from albumentations.pytorch import ToTensorV2

try:
    import segmentation_models_pytorch as smp
    SMP_AVAILABLE = True
except ImportError:
    SMP_AVAILABLE = False
    print("[WARN] segmentation_models_pytorch not found.")
    print("       Install: pip install segmentation-models-pytorch")

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
_HERE       = Path(__file__).parent
DATA_DIR    = _HERE.parent.parent / "data" / "processed"
CKPT_DIR    = _HERE / "checkpoints"
LOG_DIR     = _HERE / "logs"

# Computed from data/processed/train/images/ (1000-tile sample)
MEAN = [0.3971, 0.4192, 0.3597]
STD  = [0.0967, 0.0832, 0.0708]

NUM_CLASSES = 5
CLASS_NAMES = ["background", "building", "woodland", "water", "road"]

# Class weights — inverse of frequency to handle imbalance
# background=72%, woodland=20%, water=4%, road=1.8%, building=1.1%
# road and building doubled vs. previous run: both stalled around 0.62 and 0.77
CLASS_WEIGHTS = torch.tensor([0.15, 4.00, 0.80, 1.50, 4.00], dtype=torch.float32)

SEED = 42
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)


# ─────────────────────────────────────────────
# DATASET
# ─────────────────────────────────────────────
class LandCoverDataset(Dataset):
    """
    Loads 256x256 image + mask tiles from data/processed/images/*.jpg and masks/*.png.
    Tile lists are read from data/processed/{split}.txt (produced by preprocess.py).
    Class 0 = background = farmland (primary agriculture target).
    """
    def __init__(self, root: Path, split: str, transform=None):
        self.img_dir  = root / "images"
        self.mask_dir = root / "masks"

        split_file = root / f"{split}.txt"
        with open(split_file) as f:
            self.stems = [line.strip() for line in f if line.strip()]

        self.transform = transform

    def __len__(self):
        return len(self.stems)

    def __getitem__(self, idx):
        stem = self.stems[idx]
        img  = cv2.imread(str(self.img_dir  / f"{stem}.jpg"), cv2.IMREAD_COLOR)
        mask = cv2.imread(str(self.mask_dir / f"{stem}.png"), cv2.IMREAD_GRAYSCALE)

        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mask = np.clip(mask, 0, NUM_CLASSES - 1)

        if self.transform:
            out  = self.transform(image=img, mask=mask)
            img  = out["image"]
            mask = out["mask"].long()

        return img, mask


def get_transforms(split: str):
    if split == "train":
        return A.Compose([
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.3),
            A.RandomRotate90(p=0.5),
            A.RandomBrightnessContrast(0.2, 0.2, p=0.5),
            A.HueSaturationValue(10, 20, 10, p=0.4),
            A.GridDistortion(num_steps=5, distort_limit=0.3, p=0.3),
            A.GaussianBlur(blur_limit=(3, 5), p=0.2),
            A.Normalize(mean=MEAN, std=STD),
            ToTensorV2(),
        ])
    else:
        return A.Compose([
            A.Normalize(mean=MEAN, std=STD),
            ToTensorV2(),
        ])


def build_dataloaders(data_dir: Path, batch_size: int):
    """
    Loads tiles from data/processed/ using train.txt and val.txt produced by preprocess.py.
    Images are .jpg, masks are .png, all in flat images/ and masks/ subdirectories.
    """
    train_ds = LandCoverDataset(data_dir, "train", get_transforms("train"))
    val_ds   = LandCoverDataset(data_dir, "val",   get_transforms("val"))

    print(f"       Train: {len(train_ds)} tiles | Val: {len(val_ds)} tiles")

    train_loader = DataLoader(train_ds, batch_size=batch_size,
                              shuffle=True,  num_workers=4,
                              pin_memory=True, drop_last=True)
    val_loader   = DataLoader(val_ds,   batch_size=batch_size,
                              shuffle=False, num_workers=4,
                              pin_memory=True)

    return train_loader, val_loader


# ─────────────────────────────────────────────
# MODEL
# ─────────────────────────────────────────────
def build_model(num_classes: int = NUM_CLASSES) -> nn.Module:
    """
    U-Net with ResNet34 encoder pretrained on ImageNet.
    segmentation_models_pytorch makes this 2 lines.
    """
    if not SMP_AVAILABLE:
        raise ImportError("pip install segmentation-models-pytorch")

    model = smp.Unet(
        encoder_name    = "resnet50",
        encoder_weights = "imagenet",
        in_channels     = 3,
        classes         = num_classes,
    )
    return model


# ─────────────────────────────────────────────
# LOSS
# ─────────────────────────────────────────────
class CombinedLoss(nn.Module):
    """
    CE (weighted) + Dice + Focal.
    - CE + class weights: explicit per-class penalty scaling
    - Dice: overlap quality for imbalanced segmentation
    - Focal (gamma=2): down-weights easy background pixels, focuses on hard road/building
    """
    def __init__(self, class_weights: torch.Tensor,
                 dice_weight: float = 0.4, focal_weight: float = 0.2):
        super().__init__()
        self.ce_loss    = nn.CrossEntropyLoss(weight=class_weights)
        self.dice_loss  = smp.losses.DiceLoss(mode="multiclass", smooth=1.0)
        self.focal_loss = smp.losses.FocalLoss(mode="multiclass", gamma=2.0)
        self.dice_weight  = dice_weight
        self.focal_weight = focal_weight

    def forward(self, pred: torch.Tensor, target: torch.Tensor):
        ce_weight = 1.0 - self.dice_weight - self.focal_weight
        return (ce_weight    * self.ce_loss(pred, target)
                + self.dice_weight  * self.dice_loss(pred, target)
                + self.focal_weight * self.focal_loss(pred, target))


# ─────────────────────────────────────────────
# METRICS
# ─────────────────────────────────────────────
class IoUMeter:
    """Tracks per-class IoU and mean IoU across batches."""
    def __init__(self, num_classes: int):
        self.num_classes = num_classes
        self.reset()

    def reset(self):
        self.intersection = torch.zeros(self.num_classes)
        self.union        = torch.zeros(self.num_classes)

    def update(self, pred: torch.Tensor, target: torch.Tensor):
        pred = pred.argmax(dim=1).cpu()
        target = target.cpu()
        for cls in range(self.num_classes):
            p = (pred   == cls)
            t = (target == cls)
            self.intersection[cls] += (p & t).sum().float()
            self.union[cls]        += (p | t).sum().float()

    def compute(self) -> dict:
        iou = {}
        for cls in range(self.num_classes):
            if self.union[cls] > 0:
                iou[CLASS_NAMES[cls]] = (
                    self.intersection[cls] / self.union[cls]
                ).item()
            else:
                iou[CLASS_NAMES[cls]] = float("nan")
        valid = [v for v in iou.values() if not np.isnan(v)]
        iou["mean"] = float(np.mean(valid)) if valid else 0.0
        return iou


# ─────────────────────────────────────────────
# TRAIN / VAL LOOPS
# ─────────────────────────────────────────────
def train_one_epoch(model, loader, optimizer, criterion, device, scaler):
    model.train()
    total_loss = 0.0
    iou_meter  = IoUMeter(NUM_CLASSES)

    for batch_idx, (imgs, masks) in enumerate(loader):
        imgs  = imgs.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)

        optimizer.zero_grad()
        with torch.cuda.amp.autocast(enabled=scaler is not None):
            preds = model(imgs)
            loss  = criterion(preds, masks)

        if scaler:
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
        else:
            loss.backward()
            optimizer.step()

        total_loss += loss.item()
        iou_meter.update(preds.detach(), masks)

        if (batch_idx + 1) % 20 == 0:
            print(f"    Batch [{batch_idx+1}/{len(loader)}] "
                  f"loss: {loss.item():.4f}")

    avg_loss = total_loss / len(loader)
    iou      = iou_meter.compute()
    return avg_loss, iou


@torch.no_grad()
def validate(model, loader, criterion, device):
    model.eval()
    total_loss = 0.0
    iou_meter  = IoUMeter(NUM_CLASSES)

    for imgs, masks in loader:
        imgs  = imgs.to(device, non_blocking=True)
        masks = masks.to(device, non_blocking=True)

        preds = model(imgs)
        loss  = criterion(preds, masks)

        total_loss += loss.item()
        iou_meter.update(preds, masks)

    avg_loss = total_loss / len(loader)
    iou      = iou_meter.compute()
    return avg_loss, iou


# ─────────────────────────────────────────────
# CHECKPOINT
# ─────────────────────────────────────────────
def save_checkpoint(model, optimizer, epoch, best_miou, path: Path):
    torch.save({
        "epoch"     : epoch,
        "model"     : model.state_dict(),
        "optimizer" : optimizer.state_dict(),
        "best_miou" : best_miou,
    }, path)


def load_checkpoint(model, optimizer, path: Path, device):
    ckpt = torch.load(path, map_location=device)
    model.load_state_dict(ckpt["model"])
    optimizer.load_state_dict(ckpt["optimizer"])
    return ckpt["epoch"], ckpt["best_miou"]


# ─────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────
def log_epoch(log_path: Path, record: dict):
    logs = []
    if log_path.exists():
        with open(log_path) as f:
            logs = json.load(f)
    logs.append(record)
    with open(log_path, "w") as f:
        json.dump(logs, f, indent=2)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--epochs",     type=int,   default=30)
    p.add_argument("--batch_size", type=int,   default=8)
    p.add_argument("--lr",         type=float, default=1e-4)
    p.add_argument("--resume",     type=str,   default=None,
                   help="Path to checkpoint to resume from")
    return p.parse_args()


def main():
    args = parse_args()

    # ── Device ───────────────────────────────────────────────
    device = (
        torch.device("cuda")  if torch.cuda.is_available() else
        torch.device("mps")   if torch.backends.mps.is_available() else
        torch.device("cpu")
    )
    print(f"\n{'='*60}")
    print(f"U-Net + ResNet34 — Agriculture Segmentation Training")
    print(f"{'='*60}")
    print(f"Device     : {device}")
    print(f"Epochs     : {args.epochs}")
    print(f"Batch size : {args.batch_size}")
    print(f"LR         : {args.lr}")
    print(f"Data dir   : {DATA_DIR.resolve()}")

    CKPT_DIR.mkdir(exist_ok=True)
    LOG_DIR.mkdir(exist_ok=True)
    run_id   = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_{run_id}.json"

    # ── Data ─────────────────────────────────────────────────
    print("\n[1/4] Loading data...")
    train_loader, val_loader = build_dataloaders(DATA_DIR, args.batch_size)

    # ── Model ────────────────────────────────────────────────
    print("[2/4] Building model (U-Net + ResNet34)...")
    model = build_model(NUM_CLASSES).to(device)
    total_params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f"      Trainable params: {total_params:,}")

    # ── Loss & Optimizer ─────────────────────────────────────
    print("[3/4] Setting up loss and optimizer...")
    weights   = CLASS_WEIGHTS.to(device)
    criterion = CombinedLoss(weights, dice_weight=0.5)
    optimizer = optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)

    # Warm restarts every T_0 epochs — periodically resets LR to escape plateaus
    scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
        optimizer, T_0=10, T_mult=1, eta_min=1e-6)

    # Mixed precision (GPU only)
    scaler = torch.cuda.amp.GradScaler() if device.type == "cuda" else None

    # ── Resume ───────────────────────────────────────────────
    start_epoch = 0
    best_miou   = 0.0
    if args.resume:
        print(f"      Resuming from {args.resume}")
        start_epoch, best_miou = load_checkpoint(
            model, optimizer, Path(args.resume), device)
        print(f"      Resumed at epoch {start_epoch}, best mIoU {best_miou:.4f}")

    # ── Training Loop ────────────────────────────────────────
    print(f"[4/4] Training for {args.epochs} epochs...\n")
    for epoch in range(start_epoch, args.epochs):
        lr_now = optimizer.param_groups[0]["lr"]
        print(f"Epoch [{epoch+1}/{args.epochs}]  lr={lr_now:.2e}")

        train_loss, train_iou = train_one_epoch(
            model, train_loader, optimizer, criterion, device, scaler)
        val_loss,   val_iou   = validate(
            model, val_loader, criterion, device)

        scheduler.step()

        # Print metrics
        print(f"  Train  loss={train_loss:.4f}  mIoU={train_iou['mean']:.4f}")
        print(f"  Val    loss={val_loss:.4f}    mIoU={val_iou['mean']:.4f}")
        print("  Val IoU per class:")
        for cls in CLASS_NAMES:
            v = val_iou.get(cls, float("nan"))
            bar = "█" * int(v * 20) if not np.isnan(v) else ""
            print(f"    {cls:12s}: {v:.4f}  {bar}")

        # Save best
        miou = val_iou["mean"]
        if miou > best_miou:
            best_miou = miou
            ckpt_path = CKPT_DIR / "best_model.pth"
            save_checkpoint(model, optimizer, epoch + 1, best_miou, ckpt_path)
            print(f"  ✓ New best mIoU: {best_miou:.4f} — saved to {ckpt_path}")

        # Save latest
        save_checkpoint(model, optimizer, epoch + 1, best_miou,
                        CKPT_DIR / "latest.pth")

        # Log
        log_epoch(log_path, {
            "epoch"      : epoch + 1,
            "lr"         : lr_now,
            "train_loss" : train_loss,
            "val_loss"   : val_loss,
            "train_miou" : train_iou["mean"],
            "val_miou"   : val_iou["mean"],
            "val_iou"    : val_iou,
        })
        print()

    print("=" * 60)
    print(f"Training complete. Best val mIoU: {best_miou:.4f}")
    print(f"Best model → {CKPT_DIR / 'best_model.pth'}")
    print(f"Log        → {log_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
