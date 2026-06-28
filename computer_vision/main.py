import os
import random
import shutil

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms


def remap_mask_to_binary(mask_array, roi_labels):
    if not roi_labels:
        raise ValueError("roi_labels must be provided for binary segmentation.")
    return np.isin(mask_array, roi_labels).astype(np.int64)


def process_and_split_landcover(
    raw_img_dir,
    raw_mask_dir,
    output_root,
    patch_size=256,
    train_ratio=0.75,
):
    """
    Cut large TIFF images into patches, filter weak patches, and split train/val.
    """
    dirs = {
        "train_img": os.path.join(output_root, "train", "images"),
        "train_mask": os.path.join(output_root, "train", "masks"),
        "val_img": os.path.join(output_root, "val", "images"),
        "val_mask": os.path.join(output_root, "val", "masks"),
    }
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)

    valid_patches = []
    temp_dir = os.path.join(output_root, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    image_files = [f for f in os.listdir(raw_img_dir) if f.endswith(".tif")]
    patch_id = 0

    print("Starting patch extraction and filtering...")
    for img_name in image_files:
        img_path = os.path.join(raw_img_dir, img_name)
        mask_path = os.path.join(raw_mask_dir, img_name)

        if not os.path.exists(mask_path):
            continue

        img = cv2.imread(img_path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)

        h, w = img.shape[:2]
        for y in range(0, h - patch_size + 1, patch_size):
            for x in range(0, w - patch_size + 1, patch_size):
                patch_mask = mask[y : y + patch_size, x : x + patch_size]
                unique_labels = np.unique(patch_mask)

                bincount = np.bincount(patch_mask.flatten())
                max_class_ratio = np.max(bincount) / (patch_size * patch_size)

                if len(unique_labels) >= 2 and max_class_ratio < 0.95:
                    patch_img = img[y : y + patch_size, x : x + patch_size]
                    img_name_out = f"patch_{patch_id:05d}.tif"

                    cv2.imwrite(
                        os.path.join(temp_dir, f"img_{img_name_out}"),
                        cv2.cvtColor(patch_img, cv2.COLOR_RGB2BGR),
                    )
                    cv2.imwrite(os.path.join(temp_dir, f"mask_{img_name_out}"), patch_mask)

                    valid_patches.append(img_name_out)
                    patch_id += 1

    print(f"Finished steps 1 and 2. Valid patches: {len(valid_patches)}")

    random.shuffle(valid_patches)
    split_idx = int(train_ratio * len(valid_patches))
    train_list = valid_patches[:split_idx]
    val_list = valid_patches[split_idx:]

    print(f"Starting steps 3 and 4: train={len(train_list)}, val={len(val_list)}")

    def move_files(file_list, split_type):
        for f_name in file_list:
            shutil.move(
                os.path.join(temp_dir, f"img_{f_name}"),
                os.path.join(dirs[f"{split_type}_img"], f_name),
            )
            shutil.move(
                os.path.join(temp_dir, f"mask_{f_name}"),
                os.path.join(dirs[f"{split_type}_mask"], f_name),
            )

    move_files(train_list, "train")
    move_files(val_list, "val")

    shutil.rmtree(temp_dir)
    print("Preprocessing complete. DataLoader is ready.")


class LandcoverDataset(Dataset):
    def __init__(
        self,
        root_dir,
        train=True,
        transform=None,
        binary_mode=False,
        roi_labels=None,
    ):
        self.transform = transform
        self.binary_mode = bool(binary_mode)
        self.roi_labels = tuple(int(label) for label in (roi_labels or ()))
        if self.binary_mode and not self.roi_labels:
            raise ValueError("roi_labels are required when binary_mode=True.")

        split_folder = "train" if train else "val"
        self.img_dir = os.path.join(root_dir, split_folder, "images")
        self.mask_dir = os.path.join(root_dir, split_folder, "masks")
        self.image_filenames = sorted(os.listdir(self.img_dir))

    def __len__(self):
        return len(self.image_filenames)

    def __getitem__(self, index):
        img_name = self.image_filenames[index]

        img_path = os.path.join(self.img_dir, img_name)
        image = Image.open(img_path).convert("RGB")

        mask_path = os.path.join(self.mask_dir, img_name)
        mask = Image.open(mask_path).convert("L")

        if self.transform:
            image = self.transform(image)

        mask_array = np.array(mask, dtype=np.int64)
        if self.binary_mode:
            mask_array = remap_mask_to_binary(mask_array, self.roi_labels)

        mask = torch.from_numpy(mask_array)
        return image, mask


if __name__ == "__main__":
    RAW_IMAGES_DIR = "./data/raw/images"
    RAW_MASKS_DIR = "./data/raw/masks"
    PROCESSED_DIR = "./data/processed"

    # Run this only once when the processed dataset does not exist yet.
    # process_and_split_landcover(RAW_IMAGES_DIR, RAW_MASKS_DIR, PROCESSED_DIR)

    transform = transforms.Compose([transforms.ToTensor()])
    train_dataset = LandcoverDataset(root_dir=PROCESSED_DIR, train=True, transform=transform)

    train_dataloader = DataLoader(
        dataset=train_dataset,
        batch_size=8,
        shuffle=True,
        num_workers=4,
    )

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    for batch_images, batch_masks in train_dataloader:
        batch_images = batch_images.to(device)
        batch_masks = batch_masks.to(device)

        print(f"Batch image shape (N, C, H, W): {batch_images.shape}")
        print(f"Batch mask shape (N, H, W): {batch_masks.shape}")
        break
