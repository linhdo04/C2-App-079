from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np
import segmentation_models_pytorch as smp
import torch
from PIL import Image

from planning.path_planning import (
    build_label_binary,
    contour_to_polygon,
    extract_primary_contour,
    extract_roi_from_mask,
    plan_rcpp,
)
from planning.simulate_path_planning import plot_2d, plot_3d, save_summary


Image.MAX_IMAGE_PIXELS = None

PALETTE = np.array(
    [
        [20, 20, 20],
        [220, 95, 85],
        [70, 170, 90],
        [80, 120, 220],
        [235, 185, 60],
        [175, 95, 205],
    ],
    dtype=np.uint8,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run end-to-end segmentation inference, geometry extraction, and UAV planning."
    )
    parser.add_argument("--image-path", type=Path, required=True, help="Raw RGB image to test.")
    parser.add_argument(
        "--mask-path",
        type=Path,
        help="Optional ground-truth mask with the same extent as image-path.",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=Path("saved_models/best_unet_resnet34.pth"),
        help="Trained segmentation checkpoint.",
    )
    parser.add_argument("--encoder-name", default="resnet34", help="SMP encoder name.")
    parser.add_argument("--patch-size", type=int, default=256, help="Sliding-window tile size.")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=8,
        help="Number of tiles processed per forward pass.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("pipeline_outputs"),
        help="Root directory for generated artifacts.",
    )
    parser.add_argument(
        "--roi-labels",
        default="2",
        help="Comma-separated ROI labels in the original raw masks.",
    )
    parser.add_argument(
        "--obstacle-labels",
        default="none",
        help="Comma-separated obstacle labels. Use 'none' for the 2-class ROI/non-ROI flow.",
    )
    parser.add_argument(
        "--use-convex-hull",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use the ROI convex hull before planning.",
    )
    parser.add_argument(
        "--approx-epsilon",
        type=float,
        default=0.002,
        help="Polygon simplification ratio used after contour or hull extraction.",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        default=30.0,
        help="Sweep spacing passed to the planner.",
    )
    parser.add_argument(
        "--safety-margin",
        type=float,
        default=8.0,
        help="Obstacle safety margin used when obstacle labels are provided.",
    )
    parser.add_argument(
        "--planner-source",
        choices=["pred", "gt", "both"],
        default="both",
        help="Which mask source to pass into geometry extraction and path planning.",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "cuda"],
        default="auto",
        help="Inference device.",
    )
    parser.add_argument(
        "--skip-3d",
        action="store_true",
        help="Skip the 3D planner figure to reduce runtime.",
    )
    return parser.parse_args()


def parse_label_list(raw: str) -> list[int]:
    if raw.strip().lower() in {"", "none", "null"}:
        return []
    return [int(value.strip()) for value in raw.split(",") if value.strip()]


def remap_raw_mask_to_binary_labels(mask: np.ndarray, roi_labels: list[int]) -> np.ndarray:
    return np.isin(mask, roi_labels).astype(np.uint8)


def is_binary_label_mask(mask: np.ndarray) -> bool:
    unique_values = np.unique(mask)
    return bool(set(unique_values.tolist()).issubset({0, 1}))


def resolve_mask_path(image_path: Path, mask_path: Path | None) -> Path | None:
    if mask_path is not None:
        return mask_path

    if image_path.parent.name == "images":
        candidate = image_path.parent.parent / "masks" / image_path.name
        if candidate.exists():
            return candidate
    return None


def resolve_device(name: str) -> torch.device:
    if name == "cpu":
        return torch.device("cpu")
    if name == "cuda":
        return torch.device("cuda")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def infer_num_classes(model_path: Path) -> int:
    state_dict = torch.load(model_path, map_location="cpu")
    head_weight = state_dict.get("segmentation_head.0.weight")
    if head_weight is None or head_weight.ndim != 4:
        raise KeyError("Could not infer num_classes from segmentation_head.0.weight.")
    return int(head_weight.shape[0])


def load_model(
    model_path: Path,
    encoder_name: str,
    num_classes: int,
    device: torch.device,
) -> torch.nn.Module:
    model = smp.Unet(
        encoder_name=encoder_name,
        encoder_weights=None,
        in_channels=3,
        classes=num_classes,
    )
    state_dict = torch.load(model_path, map_location="cpu")
    model.load_state_dict(state_dict, strict=True)
    model = model.to(device)
    model.eval()
    return model


def load_rgb_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("RGB"))


def load_mask_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("L"), dtype=np.uint8)


def mask_to_color(mask: np.ndarray) -> np.ndarray:
    color = np.zeros((mask.shape[0], mask.shape[1], 3), dtype=np.uint8)
    for label in np.unique(mask):
        palette_index = int(label) % len(PALETTE)
        color[mask == label] = PALETTE[palette_index]
    return color


def overlay_segmentation(image_rgb: np.ndarray, mask: np.ndarray, alpha: float = 0.45) -> np.ndarray:
    color_mask = mask_to_color(mask)
    blended = image_rgb.astype(np.float32) * (1.0 - alpha) + color_mask.astype(np.float32) * alpha
    return np.clip(blended, 0, 255).astype(np.uint8)


def save_rgb(path: Path, image_rgb: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_rgb).save(path)


def save_gray(path: Path, image_gray: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image_gray).save(path)


def tile_predict(
    model: torch.nn.Module,
    image_rgb: np.ndarray,
    patch_size: int,
    batch_size: int,
    device: torch.device,
) -> np.ndarray:
    height, width = image_rgb.shape[:2]
    pad_h = (patch_size - (height % patch_size)) % patch_size
    pad_w = (patch_size - (width % patch_size)) % patch_size
    padded = np.pad(image_rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode="reflect")
    padded_height, padded_width = padded.shape[:2]
    prediction = np.zeros((padded_height, padded_width), dtype=np.uint8)

    tile_batch: list[torch.Tensor] = []
    coords_batch: list[tuple[int, int]] = []
    total_tiles = (padded_height // patch_size) * (padded_width // patch_size)
    processed_tiles = 0

    autocast_enabled = device.type == "cuda"

    with torch.inference_mode():
        for y in range(0, padded_height, patch_size):
            for x in range(0, padded_width, patch_size):
                patch = padded[y : y + patch_size, x : x + patch_size]
                tensor = torch.from_numpy(patch.transpose(2, 0, 1)).float() / 255.0
                tile_batch.append(tensor)
                coords_batch.append((y, x))

                if len(tile_batch) < batch_size:
                    continue

                labels = predict_batch(model, tile_batch, coords_batch, device, autocast_enabled)
                for (tile_y, tile_x), tile_labels in labels:
                    prediction[tile_y : tile_y + patch_size, tile_x : tile_x + patch_size] = tile_labels
                processed_tiles += len(tile_batch)
                print(f"Inference tiles: {processed_tiles}/{total_tiles}", end="\r", flush=True)
                tile_batch = []
                coords_batch = []

        if tile_batch:
            labels = predict_batch(model, tile_batch, coords_batch, device, autocast_enabled)
            for (tile_y, tile_x), tile_labels in labels:
                prediction[tile_y : tile_y + patch_size, tile_x : tile_x + patch_size] = tile_labels
            processed_tiles += len(tile_batch)
            print(f"Inference tiles: {processed_tiles}/{total_tiles}", end="\r", flush=True)

    print(f"Inference tiles: {processed_tiles}/{total_tiles}")
    return prediction[:height, :width]


def predict_batch(
    model: torch.nn.Module,
    tile_batch: list[torch.Tensor],
    coords_batch: list[tuple[int, int]],
    device: torch.device,
    autocast_enabled: bool,
) -> list[tuple[tuple[int, int], np.ndarray]]:
    batch = torch.stack(tile_batch, dim=0).to(device)
    with torch.autocast(device_type=device.type, enabled=autocast_enabled):
        logits = model(batch)
    labels = torch.argmax(logits, dim=1).cpu().numpy().astype(np.uint8)
    return list(zip(coords_batch, labels))


def compute_multiclass_metrics(pred_mask: np.ndarray, gt_mask: np.ndarray, num_classes: int) -> dict[str, object]:
    iou_by_class: dict[str, float | None] = {}
    valid_iou: list[float] = []
    total_correct = float((pred_mask == gt_mask).sum())
    total_pixels = float(pred_mask.size)

    for cls in range(num_classes):
        pred_inds = pred_mask == cls
        gt_inds = gt_mask == cls
        intersection = float(np.logical_and(pred_inds, gt_inds).sum())
        union = float(np.logical_or(pred_inds, gt_inds).sum())
        if union == 0.0:
            iou_by_class[str(cls)] = None
            continue
        iou = intersection / union
        iou_by_class[str(cls)] = iou
        valid_iou.append(iou)

    return {
        "pixel_accuracy": total_correct / max(total_pixels, 1.0),
        "mean_iou": sum(valid_iou) / len(valid_iou) if valid_iou else 0.0,
        "iou_by_class": iou_by_class,
    }


def compute_binary_iou(pred_binary: np.ndarray, gt_binary: np.ndarray) -> float:
    pred_mask = pred_binary > 0
    gt_mask = gt_binary > 0
    intersection = float(np.logical_and(pred_mask, gt_mask).sum())
    union = float(np.logical_or(pred_mask, gt_mask).sum())
    return intersection / max(union, 1.0)


def contour_to_points(contour: np.ndarray) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in contour[:, 0, :]]


def polygon_to_points(polygon: np.ndarray) -> list[list[float]]:
    return [[float(x), float(y)] for x, y in polygon]


def draw_geometry_overlay(
    image_rgb: np.ndarray,
    binary_mask: np.ndarray,
    main_contour: np.ndarray,
    contour_polygon: np.ndarray,
    hull_polygon: np.ndarray,
    planner_polygon: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    roi_overlay = image_rgb.copy()
    roi_pixels = binary_mask > 0
    tint = np.array([80, 200, 120], dtype=np.float32)
    roi_overlay[roi_pixels] = (
        roi_overlay[roi_pixels].astype(np.float32) * 0.55 + tint * 0.45
    ).astype(np.uint8)

    contour_view = roi_overlay.copy()
    cv2.drawContours(contour_view, [main_contour], -1, (255, 255, 255), 2)
    cv2.polylines(
        contour_view,
        [np.rint(contour_polygon).astype(np.int32)],
        True,
        (235, 185, 60),
        3,
        lineType=cv2.LINE_AA,
    )

    hull_view = roi_overlay.copy()
    cv2.drawContours(hull_view, [main_contour], -1, (255, 255, 255), 2)
    cv2.polylines(
        hull_view,
        [np.rint(hull_polygon).astype(np.int32)],
        True,
        (80, 120, 220),
        3,
        lineType=cv2.LINE_AA,
    )
    cv2.polylines(
        hull_view,
        [np.rint(planner_polygon).astype(np.int32)],
        True,
        (220, 95, 85),
        3,
        lineType=cv2.LINE_AA,
    )
    return contour_view, hull_view


def analyze_mask(
    mask: np.ndarray,
    roi_labels: list[int],
    obstacle_labels: list[int],
    approx_epsilon_ratio: float,
    use_convex_hull: bool,
    safety_margin: float,
) -> dict[str, object]:
    binary_mask = build_label_binary(mask, roi_labels)
    main_contour = extract_primary_contour(binary_mask)
    contour_polygon = contour_to_polygon(
        main_contour,
        approx_epsilon_ratio=approx_epsilon_ratio,
        use_convex_hull=False,
    )
    hull_polygon = contour_to_polygon(
        main_contour,
        approx_epsilon_ratio=approx_epsilon_ratio,
        use_convex_hull=True,
    )
    planner_polygon, obstacles = extract_roi_from_mask(
        mask,
        roi_labels=roi_labels,
        obstacle_labels=obstacle_labels,
        safety_margin=safety_margin,
        approx_epsilon_ratio=approx_epsilon_ratio,
        use_convex_hull=use_convex_hull,
    )
    return {
        "binary_mask": binary_mask,
        "main_contour": main_contour,
        "contour_polygon": contour_polygon,
        "hull_polygon": hull_polygon,
        "planner_polygon": planner_polygon,
        "obstacles": obstacles,
    }


def run_planner_stage(
    source_name: str,
    mask: np.ndarray,
    image_rgb: np.ndarray,
    output_dir: Path,
    roi_labels: list[int],
    obstacle_labels: list[int],
    approx_epsilon_ratio: float,
    use_convex_hull: bool,
    safety_margin: float,
    spacing: float,
    skip_3d: bool,
) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    analysis = analyze_mask(
        mask=mask,
        roi_labels=roi_labels,
        obstacle_labels=obstacle_labels,
        approx_epsilon_ratio=approx_epsilon_ratio,
        use_convex_hull=use_convex_hull,
        safety_margin=safety_margin,
    )

    binary_mask = analysis["binary_mask"]
    main_contour = analysis["main_contour"]
    contour_polygon = analysis["contour_polygon"]
    hull_polygon = analysis["hull_polygon"]
    planner_polygon = analysis["planner_polygon"]
    obstacles = analysis["obstacles"]

    save_gray(output_dir / f"{source_name}_roi_binary.png", binary_mask)
    contour_overlay, hull_overlay = draw_geometry_overlay(
        image_rgb=image_rgb,
        binary_mask=binary_mask,
        main_contour=main_contour,
        contour_polygon=contour_polygon,
        hull_polygon=hull_polygon,
        planner_polygon=planner_polygon,
    )
    save_rgb(output_dir / f"{source_name}_contour_overlay.png", contour_overlay)
    save_rgb(output_dir / f"{source_name}_polygon_overlay.png", hull_overlay)

    geometry_payload = {
        "source": source_name,
        "use_convex_hull": use_convex_hull,
        "roi_labels": roi_labels,
        "obstacle_labels": obstacle_labels,
        "contour_polygon": polygon_to_points(contour_polygon),
        "convex_hull_polygon": polygon_to_points(hull_polygon),
        "planner_polygon": polygon_to_points(planner_polygon),
        "raw_contour": contour_to_points(main_contour),
        "obstacles": [
            {
                "center": [float(obstacle.center[0]), float(obstacle.center[1])],
                "radius": float(obstacle.radius),
                "safety_margin": float(obstacle.safety_margin),
            }
            for obstacle in obstacles
        ],
    }
    (output_dir / f"{source_name}_geometry.json").write_text(
        json.dumps(geometry_payload, indent=2),
        encoding="utf-8",
    )

    result = plan_rcpp(
        name=f"{source_name}_{output_dir.parent.name}",
        polygon=planner_polygon,
        spacing=spacing,
        obstacles=obstacles,
    )
    plot_2d(result, output_dir / f"{source_name}_plan_2d.png")
    if not skip_3d:
        plot_3d(result, output_dir / f"{source_name}_plan_3d.png")
    save_summary([result], output_dir / f"{source_name}_summary.json")

    return {
        "source": source_name,
        "geometry_json": str((output_dir / f"{source_name}_geometry.json").resolve()),
        "roi_mask": str((output_dir / f"{source_name}_roi_binary.png").resolve()),
        "planner_summary": str((output_dir / f"{source_name}_summary.json").resolve()),
        "plan_2d": str((output_dir / f"{source_name}_plan_2d.png").resolve()),
        "plan_3d": None if skip_3d else str((output_dir / f"{source_name}_plan_3d.png").resolve()),
    }


def main() -> None:
    args = parse_args()
    raw_roi_labels = parse_label_list(args.roi_labels)
    obstacle_labels = parse_label_list(args.obstacle_labels)
    if not raw_roi_labels:
        raise ValueError("At least one ROI label is required.")

    mask_path = resolve_mask_path(args.image_path, args.mask_path)
    device = resolve_device(args.device)
    num_classes = infer_num_classes(args.model_path)
    binary_checkpoint = num_classes == 2

    sample_dir = args.output_dir / args.image_path.stem
    sample_dir.mkdir(parents=True, exist_ok=True)

    print(f"Image: {args.image_path.resolve()}")
    if mask_path is not None:
        print(f"Ground-truth mask: {mask_path.resolve()}")
    print(f"Checkpoint: {args.model_path.resolve()}")
    print(f"Device: {device}")
    print(f"Num classes inferred from checkpoint: {num_classes}")
    if binary_checkpoint:
        print("Checkpoint mode: binary ROI/non-ROI")
    else:
        print("Checkpoint mode: multiclass")

    image_rgb = load_rgb_image(args.image_path)
    gt_mask = load_mask_image(mask_path) if mask_path is not None else None
    if gt_mask is not None and binary_checkpoint and not is_binary_label_mask(gt_mask):
        gt_mask = remap_raw_mask_to_binary_labels(gt_mask, raw_roi_labels)

    model = load_model(
        model_path=args.model_path,
        encoder_name=args.encoder_name,
        num_classes=num_classes,
        device=device,
    )

    t0 = time.perf_counter()
    pred_mask = tile_predict(
        model=model,
        image_rgb=image_rgb,
        patch_size=int(args.patch_size),
        batch_size=int(args.batch_size),
        device=device,
    )
    inference_seconds = time.perf_counter() - t0

    inference_dir = sample_dir / "01_inference"
    save_rgb(inference_dir / "image_rgb.png", image_rgb)
    save_gray(inference_dir / "pred_mask.png", pred_mask)
    save_rgb(inference_dir / "pred_mask_color.png", mask_to_color(pred_mask))
    save_rgb(inference_dir / "pred_overlay.png", overlay_segmentation(image_rgb, pred_mask))

    summary_payload: dict[str, object] = {
        "image_path": str(args.image_path.resolve()),
        "mask_path": None if mask_path is None else str(mask_path.resolve()),
        "model_path": str(args.model_path.resolve()),
        "num_classes": num_classes,
        "patch_size": int(args.patch_size),
        "batch_size": int(args.batch_size),
        "device": str(device),
        "inference_seconds": inference_seconds,
        "raw_roi_labels": raw_roi_labels,
        "obstacle_labels": obstacle_labels,
        "planner_roi_labels": [1] if binary_checkpoint else raw_roi_labels,
        "use_convex_hull": bool(args.use_convex_hull),
        "spacing": float(args.spacing),
        "artifacts": {
            "pred_mask": str((inference_dir / "pred_mask.png").resolve()),
            "pred_mask_color": str((inference_dir / "pred_mask_color.png").resolve()),
            "pred_overlay": str((inference_dir / "pred_overlay.png").resolve()),
        },
        "planner_outputs": {},
    }

    if gt_mask is not None:
        if gt_mask.shape != pred_mask.shape:
            raise ValueError(
                f"Ground-truth mask shape {gt_mask.shape} does not match prediction shape {pred_mask.shape}."
            )
        save_gray(inference_dir / "gt_mask.png", gt_mask)
        save_rgb(inference_dir / "gt_mask_color.png", mask_to_color(gt_mask))
        save_rgb(inference_dir / "gt_overlay.png", overlay_segmentation(image_rgb, gt_mask))

        planner_roi_labels = [1] if binary_checkpoint else raw_roi_labels
        pred_binary = build_label_binary(pred_mask, planner_roi_labels)
        gt_binary = build_label_binary(gt_mask, planner_roi_labels)
        metrics = compute_multiclass_metrics(pred_mask, gt_mask, num_classes)
        metrics["binary_roi_iou"] = compute_binary_iou(pred_binary, gt_binary)
        (sample_dir / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
        summary_payload["metrics"] = metrics
        summary_payload["artifacts"]["gt_mask"] = str((inference_dir / "gt_mask.png").resolve())
        summary_payload["artifacts"]["gt_overlay"] = str((inference_dir / "gt_overlay.png").resolve())

    planner_targets: list[tuple[str, np.ndarray]] = []
    if args.planner_source in {"pred", "both"}:
        planner_targets.append(("prediction", pred_mask))
    if args.planner_source in {"gt", "both"} and gt_mask is not None:
        planner_targets.append(("ground_truth", gt_mask))

    planner_roi_labels = [1] if binary_checkpoint else raw_roi_labels
    planner_obstacle_labels = [] if binary_checkpoint else obstacle_labels

    for source_name, mask_source in planner_targets:
        planning_dir = sample_dir / "02_geometry_and_planning"
        try:
            planner_result = run_planner_stage(
                source_name=source_name,
                mask=mask_source,
                image_rgb=image_rgb,
                output_dir=planning_dir,
                roi_labels=planner_roi_labels,
                obstacle_labels=planner_obstacle_labels,
                approx_epsilon_ratio=float(args.approx_epsilon),
                use_convex_hull=bool(args.use_convex_hull),
                safety_margin=float(args.safety_margin),
                spacing=float(args.spacing),
                skip_3d=bool(args.skip_3d),
            )
            summary_payload["planner_outputs"][source_name] = planner_result
        except Exception as exc:  # pragma: no cover - keeps the pipeline report usable
            summary_payload["planner_outputs"][source_name] = {
                "source": source_name,
                "error": str(exc),
            }

    summary_path = sample_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary_payload, indent=2), encoding="utf-8")

    print(f"Inference finished in {inference_seconds:.2f} seconds.")
    print(f"Artifacts saved to: {sample_dir.resolve()}")
    if "metrics" in summary_payload:
        metrics = summary_payload["metrics"]
        print(
            f"Prediction vs GT -> pixel_acc={metrics['pixel_accuracy']:.4f}, "
            f"mean_iou={metrics['mean_iou']:.4f}, binary_roi_iou={metrics['binary_roi_iou']:.4f}"
        )
    for source_name, payload in summary_payload["planner_outputs"].items():
        if "error" in payload:
            print(f"{source_name}: planner stage failed -> {payload['error']}")
        else:
            print(f"{source_name}: planner artifacts ready.")


if __name__ == "__main__":
    main()
