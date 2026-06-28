import argparse
import os
from pathlib import Path

import segmentation_models_pytorch as smp
import torch
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm

from computer_vision.main import LandcoverDataset


def calculate_iou(preds, labels, num_classes):
    """Compute mean IoU across the classes present in a batch."""
    preds = torch.argmax(preds, dim=1)
    iou_list = []
    for cls in range(num_classes):
        pred_inds = preds == cls
        target_inds = labels == cls
        intersection = (pred_inds[target_inds]).long().sum().item()
        union = pred_inds.long().sum().item() + target_inds.long().sum().item() - intersection
        if union == 0:
            continue
        iou_list.append(float(intersection) / float(max(union, 1)))
    return sum(iou_list) / len(iou_list) if iou_list else 0


def parse_label_list(raw):
    if raw.strip().lower() in {"", "none", "null"}:
        return []
    return [int(value.strip()) for value in raw.split(",") if value.strip()]


def parse_args():
    parser = argparse.ArgumentParser(description="Train land-cover segmentation models.")
    parser.add_argument(
        "--task",
        choices=["binary", "multiclass"],
        default="multiclass",
        help="Train the default multiclass model or an optional binary ROI/non-ROI model.",
    )
    parser.add_argument(
        "--processed-dir",
        default="./data/processed",
        help="Directory containing processed train/val patch folders.",
    )
    parser.add_argument(
        "--roi-labels",
        default="2",
        help="Raw mask labels treated as ROI when --task=binary.",
    )
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=25)
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--num-workers", type=int, default=2)
    parser.add_argument("--encoder-name", default="resnet34")
    parser.add_argument(
        "--checkpoint-path",
        help="Override checkpoint path. Defaults depend on --task.",
    )
    return parser.parse_args()


def resolve_checkpoint_path(args):
    if args.checkpoint_path:
        return Path(args.checkpoint_path)
    if args.task == "binary":
        return Path("saved_models/best_unet_resnet34_binary_roi.pth")
    return Path("saved_models/best_unet_resnet34.pth")


def build_datasets(args):
    transform = transforms.Compose([transforms.ToTensor()])
    binary_mode = args.task == "binary"
    roi_labels = parse_label_list(args.roi_labels) if binary_mode else None

    train_dataset = LandcoverDataset(
        root_dir=args.processed_dir,
        train=True,
        transform=transform,
        binary_mode=binary_mode,
        roi_labels=roi_labels,
    )
    val_dataset = LandcoverDataset(
        root_dir=args.processed_dir,
        train=False,
        transform=transform,
        binary_mode=binary_mode,
        roi_labels=roi_labels,
    )
    return train_dataset, val_dataset, roi_labels or []


def build_model(args, num_classes, device):
    model = smp.Unet(
        encoder_name=args.encoder_name,
        encoder_weights="imagenet",
        in_channels=3,
        classes=num_classes,
    )
    return model.to(device)


def main():
    args = parse_args()
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    checkpoint_path = resolve_checkpoint_path(args)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    train_dataset, val_dataset, roi_labels = build_datasets(args)
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.num_workers,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.num_workers,
    )

    num_classes = 2 if args.task == "binary" else 5
    model = build_model(args, num_classes, device)
    criterion = smp.losses.DiceLoss(mode="multiclass")
    optimizer = optim.AdamW(model.parameters(), lr=args.learning_rate)

    print(f"Starting training on device: {device}")
    print(f"Task: {args.task}")
    if args.task == "binary":
        print(f"Binary ROI labels from raw masks: {roi_labels}")
    print(f"Checkpoint: {checkpoint_path.resolve()}")

    best_iou = 0.0
    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        train_iou = 0.0

        train_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Train]")
        for images, masks in train_bar:
            images, masks = images.to(device), masks.to(device)

            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, masks)

            loss.backward()
            optimizer.step()

            train_loss += loss.item()
            train_iou += calculate_iou(outputs, masks, num_classes)
            train_bar.set_postfix(loss=f"{loss.item():.4f}")

        model.eval()
        val_loss = 0.0
        val_iou = 0.0

        val_bar = tqdm(val_loader, desc=f"Epoch {epoch + 1}/{args.epochs} [Val]")
        with torch.no_grad():
            for images, masks in val_bar:
                images, masks = images.to(device), masks.to(device)

                outputs = model(images)
                loss = criterion(outputs, masks)

                val_loss += loss.item()
                val_iou += calculate_iou(outputs, masks, num_classes)

        avg_train_loss = train_loss / len(train_loader)
        avg_train_iou = train_iou / len(train_loader)
        avg_val_loss = val_loss / len(val_loader)
        avg_val_iou = val_iou / len(val_loader)

        print(f"-> Train Loss: {avg_train_loss:.4f} | Train Mean IoU: {avg_train_iou:.4f}")
        print(f"-> Val Loss:   {avg_val_loss:.4f} | Val Mean IoU:   {avg_val_iou:.4f}")

        if avg_val_iou > best_iou:
            best_iou = avg_val_iou
            torch.save(model.state_dict(), checkpoint_path)
            print(f"[*] Saved best model with Val IoU: {best_iou:.4f}")
        print("-" * 50)

    print("Training complete.")


if __name__ == "__main__":
    main()
