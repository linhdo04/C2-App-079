from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation, PillowWriter
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

from planning.path_planning import CircularObstacle, extract_roi_from_mask, plan_rcpp
from scenario_reference import REFERENCE_SCENARIOS


def _scenario_payload() -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for key, spec in REFERENCE_SCENARIOS.items():
        payload[key] = {
            "polygon": [list(point) for point in spec.polygon],
            "spacing": float(spec.spacing),
            "obstacles": [
                CircularObstacle(
                    center=obstacle.center,
                    radius=obstacle.radius,
                    safety_margin=obstacle.safety_margin,
                )
                for obstacle in spec.obstacles
            ],
        }
    return payload


PAPER_SCENARIOS = _scenario_payload()

ACTIVE_ANIMATIONS = []


def setup_2d_axes(result):
    fig, ax = plt.subplots(figsize=(8, 7))
    polygon = result.polygon
    ax.fill(polygon[:, 0], polygon[:, 1], color="#dcefd2", alpha=0.9, label="ROI")
    ax.plot(
        np.r_[polygon[:, 0], polygon[0, 0]],
        np.r_[polygon[:, 1], polygon[0, 1]],
        color="#356859",
        linewidth=2,
    )

    for index, obstacle in enumerate(result.obstacles):
        circle = plt.Circle(
            obstacle.center,
            obstacle.effective_radius,
            color="#d1495b",
            alpha=0.28,
            label="Obstacle" if index == 0 else None,
        )
        ax.add_patch(circle)

    ax.set_title(result.name)
    ax.set_aspect("equal", adjustable="box")
    ax.invert_yaxis()
    ax.grid(alpha=0.25)
    return fig, ax


def plot_2d(result, output_path: Path, show: bool = False) -> None:
    fig, ax = setup_2d_axes(result)
    ax.plot(
        result.path[:, 0],
        result.path[:, 1],
        color="#1d3557",
        linewidth=1.5,
        alpha=0.55,
        label="Raw path",
    )
    ax.plot(
        result.smooth_path[:, 0],
        result.smooth_path[:, 1],
        color="#f77f00",
        linewidth=2.4,
        label="Cubic spline",
    )
    ax.scatter(result.path[0, 0], result.path[0, 1], c="#2a9d8f", s=60, label="Start")
    ax.scatter(result.path[-1, 0], result.path[-1, 1], c="#e63946", s=60, label="End")

    metrics = (
        f"angle={result.orientation_deg:.2f} deg\n"
        f"sweeps={result.sweep_lines}\n"
        f"turns={result.turns}\n"
        f"coverage={result.coverage_ratio * 100:.2f}%\n"
        f"overlap={result.overlap_ratio * 100:.2f}%\n"
        f"cost={result.cost:.2f}"
    )
    ax.text(
        0.02,
        0.98,
        metrics,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.86, "edgecolor": "#999999"},
    )

    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    if not show:
        plt.close(fig)


def plot_3d(result, output_path: Path, flight_height: float = 18.0, show: bool = False) -> None:
    fig = plt.figure(figsize=(8, 7))
    ax = fig.add_subplot(111, projection="3d")
    polygon3d = np.column_stack([result.polygon, np.zeros(len(result.polygon))])
    poly = Poly3DCollection([polygon3d], alpha=0.28, facecolor="#97c1a9", edgecolor="#356859")
    ax.add_collection3d(poly)

    ax.plot(
        result.smooth_path[:, 0],
        result.smooth_path[:, 1],
        np.full(len(result.smooth_path), flight_height),
        color="#f77f00",
        linewidth=2.2,
    )
    ax.scatter(
        [result.smooth_path[0, 0], result.smooth_path[-1, 0]],
        [result.smooth_path[0, 1], result.smooth_path[-1, 1]],
        [flight_height, flight_height],
        c=["#2a9d8f", "#e63946"],
        s=45,
    )

    theta = np.linspace(0.0, 2.0 * np.pi, 80)
    for obstacle in result.obstacles:
        x = obstacle.center[0] + obstacle.effective_radius * np.cos(theta)
        y = obstacle.center[1] + obstacle.effective_radius * np.sin(theta)
        z = np.zeros_like(theta)
        ax.plot(x, y, z, color="#d1495b", linewidth=1.5)
        ax.plot(x, y, np.full_like(theta, flight_height), color="#d1495b", linewidth=0.8, alpha=0.35)

    ax.set_title(f"{result.name} - 3D simulation")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_zlabel("Z")
    ax.view_init(elev=28, azim=-58)
    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
    if not show:
        plt.close(fig)


def resample_animation_path(points: np.ndarray, max_frames: int) -> np.ndarray:
    if len(points) <= max_frames:
        return points
    indices = np.linspace(0, len(points) - 1, max_frames, dtype=int)
    return points[indices]


def animate_2d(
    result,
    output_path: Path,
    show: bool = False,
    fps: int = 20,
    max_frames: int = 450,
) -> None:
    fig, ax = setup_2d_axes(result)
    ax.plot(
        result.path[:, 0],
        result.path[:, 1],
        color="#1d3557",
        linewidth=1.0,
        alpha=0.35,
        label="Raw path",
    )
    ax.plot(
        result.smooth_path[:, 0],
        result.smooth_path[:, 1],
        color="#adb5bd",
        linewidth=1.4,
        alpha=0.5,
        linestyle="--",
        label="Reference path",
    )
    ax.scatter(result.path[0, 0], result.path[0, 1], c="#2a9d8f", s=60, label="Start")
    ax.scatter(result.path[-1, 0], result.path[-1, 1], c="#e63946", s=60, label="End")

    anim_points = resample_animation_path(result.smooth_path, max_frames=max_frames)
    animated_line, = ax.plot([], [], color="#f77f00", linewidth=2.8, label="Animated path")
    uav_marker = ax.scatter([], [], c="#ff9f1c", s=100, edgecolors="black", linewidths=0.8, label="UAV")
    progress_text = ax.text(
        0.02,
        0.98,
        "",
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=10,
        bbox={"facecolor": "white", "alpha": 0.86, "edgecolor": "#999999"},
    )

    metrics = (
        f"angle={result.orientation_deg:.2f} deg\n"
        f"sweeps={result.sweep_lines}\n"
        f"turns={result.turns}\n"
        f"coverage={result.coverage_ratio * 100:.2f}%\n"
        f"overlap={result.overlap_ratio * 100:.2f}%"
    )

    def init():
        animated_line.set_data([], [])
        uav_marker.set_offsets(np.empty((0, 2)))
        progress_text.set_text(metrics + "\nprogress=0.0%")
        return animated_line, uav_marker, progress_text

    def update(frame_idx: int):
        current = anim_points[: frame_idx + 1]
        animated_line.set_data(current[:, 0], current[:, 1])
        uav_marker.set_offsets(current[-1:])
        progress = 100.0 * frame_idx / max(len(anim_points) - 1, 1)
        progress_text.set_text(metrics + f"\nprogress={progress:.1f}%")
        return animated_line, uav_marker, progress_text

    animation = FuncAnimation(
        fig,
        update,
        frames=len(anim_points),
        init_func=init,
        interval=max(1, int(1000 / max(fps, 1))),
        blit=False,
        repeat=True,
    )
    ax.legend(loc="lower right")
    fig.tight_layout()
    animation.save(output_path, writer=PillowWriter(fps=max(fps, 1)))
    if show:
        ACTIVE_ANIMATIONS.append(animation)
    if not show:
        plt.close(fig)


def save_summary(results, output_path: Path) -> None:
    payload = []
    for result in results:
        payload.append(
            {
                "name": result.name,
                "orientation_deg": round(result.orientation_deg, 4),
                "sweep_lines": result.sweep_lines,
                "turns": result.turns,
                "coverage_ratio": round(result.coverage_ratio, 6),
                "overlap_ratio": round(result.overlap_ratio, 6),
                "cost": round(result.cost, 4),
                "path_length": round(
                    float(np.linalg.norm(result.path[1:] - result.path[:-1], axis=1).sum()),
                    4,
                )
                if len(result.path) > 1
                else 0.0,
            }
        )
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_paper_scenarios(
    output_dir: Path,
    show: bool = False,
    animate: bool = False,
    animation_fps: int = 20,
    animation_max_frames: int = 450,
) -> list:
    results = []
    for name, scenario in PAPER_SCENARIOS.items():
        result = plan_rcpp(
            name=name,
            polygon=scenario["polygon"],
            spacing=float(scenario["spacing"]),
            obstacles=scenario["obstacles"],
        )
        plot_2d(result, output_dir / f"{name}_2d.png", show=show and not animate)
        plot_3d(result, output_dir / f"{name}_3d.png", show=show and not animate)
        if animate:
            animate_2d(
                result,
                output_dir / f"{name}_animation.gif",
                show=show,
                fps=animation_fps,
                max_frames=animation_max_frames,
            )
        results.append(result)
    return results


def run_mask_scenario(
    output_dir: Path,
    mask_path: Path,
    spacing: float,
    roi_labels: list[int],
    obstacle_labels: list[int],
    use_convex_hull: bool = False,
    show: bool = False,
    animate: bool = False,
    animation_fps: int = 20,
    animation_max_frames: int = 450,
) -> list:
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Could not read mask: {mask_path}")
    polygon, obstacles = extract_roi_from_mask(
        mask,
        roi_labels=roi_labels,
        obstacle_labels=obstacle_labels,
        use_convex_hull=use_convex_hull,
    )
    name = mask_path.stem
    result = plan_rcpp(
        name=name,
        polygon=polygon,
        spacing=spacing,
        obstacles=obstacles,
    )
    plot_2d(result, output_dir / f"{name}_2d.png", show=show and not animate)
    plot_3d(result, output_dir / f"{name}_3d.png", show=show and not animate)
    if animate:
        animate_2d(
            result,
            output_dir / f"{name}_animation.gif",
            show=show,
            fps=animation_fps,
            max_frames=animation_max_frames,
        )
    return [result]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RCPP + BECD simulations.")
    parser.add_argument(
        "--output-dir",
        default="simulation_outputs",
        help="Directory for plots and JSON summary.",
    )
    parser.add_argument(
        "--mode",
        choices=["paper", "mask"],
        default="paper",
        help="Use either the PDF example polygons or a mask-derived ROI.",
    )
    parser.add_argument("--mask-path", help="Mask path for mode=mask.")
    parser.add_argument("--spacing", type=float, default=30.0, help="Sweep spacing.")
    parser.add_argument("--roi-labels", default="2", help="Comma-separated ROI labels.")
    parser.add_argument(
        "--use-convex-hull",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use the ROI convex hull before polygon simplification.",
    )
    parser.add_argument(
        "--obstacle-labels",
        default="1,3,4",
        help="Comma-separated obstacle labels for mode=mask.",
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Open matplotlib windows in addition to saving PNG files.",
    )
    parser.add_argument(
        "--animate",
        action="store_true",
        help="Generate a dynamic 2D animation as a GIF.",
    )
    parser.add_argument(
        "--animation-fps",
        type=int,
        default=20,
        help="Frames per second for the GIF animation.",
    )
    parser.add_argument(
        "--animation-max-frames",
        type=int,
        default=450,
        help="Maximum number of frames after path resampling.",
    )
    return parser.parse_args()


def parse_label_list(raw: str) -> list[int]:
    if raw.strip().lower() in {"", "none", "null"}:
        return []
    return [int(value) for value in raw.split(",") if value.strip()]


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "paper":
        results = run_paper_scenarios(
            output_dir,
            show=args.show,
            animate=args.animate,
            animation_fps=args.animation_fps,
            animation_max_frames=args.animation_max_frames,
        )
    else:
        if not args.mask_path:
            raise ValueError("--mask-path is required when --mode=mask.")
        roi_labels = parse_label_list(args.roi_labels)
        obstacle_labels = parse_label_list(args.obstacle_labels)
        results = run_mask_scenario(
            output_dir,
            mask_path=Path(args.mask_path),
            spacing=float(args.spacing),
            roi_labels=roi_labels,
            obstacle_labels=obstacle_labels,
            use_convex_hull=bool(args.use_convex_hull),
            show=args.show,
            animate=args.animate,
            animation_fps=args.animation_fps,
            animation_max_frames=args.animation_max_frames,
        )

    save_summary(results, output_dir / "summary.json")
    print(f"Saved outputs to: {output_dir.resolve()}")
    if args.animate:
        print("GIF animations were saved to the output directory.")
    if args.show:
        print("Matplotlib windows are open. Close them to finish the script.")
        plt.show()


if __name__ == "__main__":
    main()
