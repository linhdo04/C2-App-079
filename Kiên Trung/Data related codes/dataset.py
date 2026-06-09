"""
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
