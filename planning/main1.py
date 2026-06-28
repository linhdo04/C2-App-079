from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("OPENCV_LOG_LEVEL", "ERROR")

import cv2
import numpy as np

from planning.UAV import UAV
from planning.path_planning import (
    CircularObstacle,
    dedupe_path,
    extract_roi_from_mask,
    plan_rcpp,
    route_segment,
)
from scenario_reference import REFERENCE_SCENARIOS, SCENARIO_ALIASES


def _scenario_payload() -> dict[str, dict[str, object]]:
    payload: dict[str, dict[str, object]] = {}
    for key, spec in REFERENCE_SCENARIOS.items():
        payload[key] = {
            "polygon": [list(point) for point in spec.polygon],
            "spacing": float(spec.spacing),
            "obstacles": [
                {
                    "center": list(obstacle.center),
                    "radius": float(obstacle.radius),
                    "safety_margin": float(obstacle.safety_margin),
                }
                for obstacle in spec.obstacles
            ],
        }
    return payload


PAPER_SCENARIOS = _scenario_payload()

DEFAULT_RAW_MASK_DIR = Path("data/raw/masks")
DEFAULT_RAW_MASK_NAME = "M-33-20-D-c-4-2.tif"


@dataclass
class ScenarioConfig:
    name: str
    polygon: np.ndarray
    spacing: float
    obstacles: list[CircularObstacle]
    start: np.ndarray | None = None
    end: np.ndarray | None = None
    source_path: Path | None = None
    geometry_scale: float = 1.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pygame simulator for the UAV coverage path planning problem."
    )
    parser.add_argument("--mode", choices=["paper", "mask", "json", "raw"], default="raw")
    parser.add_argument(
        "--scenario",
        default="paper_obstacle",
        help="Built-in paper scenario name when --mode=paper.",
    )
    parser.add_argument(
        "--scenario-json",
        type=Path,
        help="Path to a JSON scenario exported by gen_test.py.",
    )
    parser.add_argument("--mask-path", type=Path, help="Mask path when --mode=mask.")
    parser.add_argument(
        "--raw-mask-dir",
        type=Path,
        default=DEFAULT_RAW_MASK_DIR,
        help="Directory containing raw mask TIFF files.",
    )
    parser.add_argument(
        "--mask-name",
        help="Mask filename inside raw-mask-dir, for example M-33-20-D-c-4-2.tif.",
    )
    parser.add_argument(
        "--mask-index",
        type=int,
        help="Index inside the sorted raw-mask-dir listing.",
    )
    parser.add_argument(
        "--spacing",
        type=float,
        help="Override sweep spacing. If omitted, scenario default is used.",
    )
    parser.add_argument(
        "--target-max-span",
        type=float,
        default=420.0,
        help="Normalize mask geometry so its largest span matches this value. Use 0 to disable.",
    )
    parser.add_argument(
        "--mask-contour-epsilon",
        type=float,
        default=0.002,
        help="Contour simplification ratio used when extracting ROI from a mask.",
    )
    parser.add_argument(
        "--use-convex-hull",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Use the ROI convex hull before polygon simplification.",
    )
    parser.add_argument("--roi-labels", default="2", help="ROI labels for mask mode.")
    parser.add_argument(
        "--obstacle-labels",
        default="1,3,4",
        help="Obstacle labels for mask mode.",
    )
    parser.add_argument(
        "--safety-margin",
        type=float,
        default=8.0,
        help="Safety margin around circular obstacles in mask mode.",
    )
    parser.add_argument(
        "--flight-path",
        choices=["smooth", "raw"],
        default="smooth",
        help="Path used by the UAV during the pygame simulation.",
    )
    parser.add_argument(
        "--reference-path",
        choices=["smooth", "raw", "none"],
        default="raw",
        help="Reference overlay drawn in the pygame window.",
    )
    parser.add_argument("--speed", type=float, default=180.0, help="UAV speed in px/s.")
    parser.add_argument("--fps", type=int, default=60, help="Target FPS for pygame.")
    parser.add_argument("--window-width", type=int, default=1280)
    parser.add_argument("--window-height", type=int, default=900)
    parser.add_argument(
        "--list-scenarios",
        action="store_true",
        help="List built-in paper scenarios and exit.",
    )
    parser.add_argument(
        "--list-raw-masks",
        action="store_true",
        help="List masks found in raw-mask-dir and exit.",
    )
    return parser.parse_args()


def parse_label_list(raw: str) -> list[int]:
    if raw.strip().lower() in {"", "none", "null"}:
        return []
    return [int(value.strip()) for value in raw.split(",") if value.strip()]


def to_point(raw) -> np.ndarray | None:
    if raw is None:
        return None
    point = np.asarray(raw, dtype=float)
    if point.shape != (2,):
        raise ValueError("Expected a point of shape (2,).")
    return point


def to_obstacles(raw_obstacles) -> list[CircularObstacle]:
    obstacles: list[CircularObstacle] = []
    for obstacle in raw_obstacles:
        obstacles.append(
            CircularObstacle(
                center=tuple(float(value) for value in obstacle["center"]),
                radius=float(obstacle["radius"]),
                safety_margin=float(obstacle.get("safety_margin", 0.0)),
            )
        )
    return obstacles


def apply_obstacle_safety_margin(
    obstacles: list[CircularObstacle],
    safety_margin: float,
) -> list[CircularObstacle]:
    return [
        CircularObstacle(
            center=obstacle.center,
            radius=float(obstacle.radius),
            safety_margin=float(safety_margin),
        )
        for obstacle in obstacles
    ]


def normalize_scenario_geometry(
    scenario: ScenarioConfig,
    target_max_span: float,
) -> ScenarioConfig:
    if target_max_span <= 0.0:
        return scenario

    polygon = np.asarray(scenario.polygon, dtype=float)
    min_corner = polygon.min(axis=0)
    max_corner = polygon.max(axis=0)

    for obstacle in scenario.obstacles:
        radius = float(obstacle.radius)
        cx, cy = obstacle.center
        min_corner = np.minimum(min_corner, np.array([cx - radius, cy - radius], dtype=float))
        max_corner = np.maximum(max_corner, np.array([cx + radius, cy + radius], dtype=float))

    span = np.maximum(max_corner - min_corner, 1.0)
    max_span = float(max(span[0], span[1]))
    if max_span <= 1e-6:
        return scenario

    scale = float(target_max_span / max_span)
    shift = -min_corner

    polygon_scaled = (polygon + shift) * scale
    start_scaled = None if scenario.start is None else (np.asarray(scenario.start, dtype=float) + shift) * scale
    end_scaled = None if scenario.end is None else (np.asarray(scenario.end, dtype=float) + shift) * scale
    obstacles_scaled = [
        CircularObstacle(
            center=tuple(((np.asarray(obstacle.center, dtype=float) + shift) * scale).tolist()),
            radius=float(obstacle.radius * scale),
            safety_margin=float(obstacle.safety_margin * scale),
        )
        for obstacle in scenario.obstacles
    ]

    return ScenarioConfig(
        name=scenario.name,
        polygon=polygon_scaled,
        spacing=scenario.spacing,
        obstacles=obstacles_scaled,
        start=start_scaled,
        end=end_scaled,
        source_path=scenario.source_path,
        geometry_scale=scenario.geometry_scale * scale,
    )


def list_raw_mask_files(mask_dir: Path) -> list[Path]:
    if not mask_dir.exists():
        raise FileNotFoundError(f"Raw mask directory does not exist: {mask_dir}")
    if not mask_dir.is_dir():
        raise NotADirectoryError(f"Raw mask path is not a directory: {mask_dir}")
    return sorted(mask_dir.glob("*.tif"))


def print_raw_mask_listing(mask_dir: Path) -> None:
    mask_files = list_raw_mask_files(mask_dir)
    if not mask_files:
        print(f"No .tif mask files found in: {mask_dir.resolve()}")
        return

    print(f"Raw mask directory: {mask_dir.resolve()}")
    for index, path in enumerate(mask_files):
        print(f"[{index:02d}] {path.name}")


def resolve_mask_path(args: argparse.Namespace) -> Path:
    if args.mask_path is not None:
        return args.mask_path

    mask_files = list_raw_mask_files(args.raw_mask_dir)
    if not mask_files:
        raise FileNotFoundError(f"No .tif mask files found in: {args.raw_mask_dir.resolve()}")

    if args.mask_name:
        lookup = args.mask_name.casefold()
        for path in mask_files:
            if path.name.casefold() == lookup or path.stem.casefold() == lookup:
                return path
        available = ", ".join(path.name for path in mask_files[:8])
        raise FileNotFoundError(
            f"Mask '{args.mask_name}' was not found in {args.raw_mask_dir.resolve()}. "
            f"Examples: {available}"
        )

    if args.mask_index is not None:
        if not 0 <= args.mask_index < len(mask_files):
            raise IndexError(
                f"mask-index={args.mask_index} is out of range for {len(mask_files)} masks."
            )
        return mask_files[args.mask_index]

    for path in mask_files:
        if path.name == DEFAULT_RAW_MASK_NAME:
            return path
    return mask_files[0]


def load_paper_scenario(name: str, spacing_override: float | None) -> ScenarioConfig:
    name = SCENARIO_ALIASES.get(name, name)
    if name not in PAPER_SCENARIOS:
        valid = ", ".join(sorted(PAPER_SCENARIOS))
        raise ValueError(f"Unknown scenario '{name}'. Available: {valid}")
    payload = PAPER_SCENARIOS[name]
    spacing = float(spacing_override if spacing_override is not None else payload["spacing"])
    return ScenarioConfig(
        name=name,
        polygon=np.asarray(payload["polygon"], dtype=float),
        spacing=spacing,
        obstacles=to_obstacles(payload["obstacles"]),
    )


def load_json_scenario(path: Path, spacing_override: float | None) -> ScenarioConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    spacing = float(spacing_override if spacing_override is not None else payload["spacing"])
    return ScenarioConfig(
        name=str(payload.get("name", path.stem)),
        polygon=np.asarray(payload["polygon"], dtype=float),
        spacing=spacing,
        obstacles=to_obstacles(payload.get("obstacles", [])),
        start=to_point(payload.get("start")),
        end=to_point(payload.get("end")),
        source_path=path,
    )


def load_mask_scenario(args: argparse.Namespace) -> ScenarioConfig:
    mask_path = resolve_mask_path(args)
    mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)
    if mask is None:
        raise FileNotFoundError(f"Could not read mask: {mask_path}")

    polygon, raw_obstacles = extract_roi_from_mask(
        mask,
        roi_labels=parse_label_list(args.roi_labels),
        obstacle_labels=parse_label_list(args.obstacle_labels),
        safety_margin=0.0,
        approx_epsilon_ratio=float(args.mask_contour_epsilon),
        use_convex_hull=bool(args.use_convex_hull),
    )
    spacing = float(args.spacing if args.spacing is not None else 30.0)
    scenario = ScenarioConfig(
        name=mask_path.stem,
        polygon=polygon,
        spacing=spacing,
        obstacles=raw_obstacles,
        source_path=mask_path,
    )
    scenario = normalize_scenario_geometry(scenario, float(args.target_max_span))
    scenario.obstacles = apply_obstacle_safety_margin(
        scenario.obstacles,
        float(args.safety_margin),
    )
    return scenario


def resolve_scenario(args: argparse.Namespace) -> ScenarioConfig:
    if args.mode == "paper":
        return load_paper_scenario(args.scenario, args.spacing)
    if args.mode == "json":
        if args.scenario_json is None:
            raise ValueError("--scenario-json is required when --mode=json.")
        return load_json_scenario(args.scenario_json, args.spacing)
    return load_mask_scenario(args)


def resolve_mission_end(scenario: ScenarioConfig) -> np.ndarray | None:
    if scenario.end is not None:
        return scenario.end
    if scenario.start is not None:
        return scenario.start
    return None


def build_planning_result(scenario: ScenarioConfig):
    mission_end = resolve_mission_end(scenario)
    start_cost = scenario.start if scenario.start is not None and mission_end is not None else None
    end_cost = mission_end if scenario.start is not None and mission_end is not None else None
    return plan_rcpp(
        name=scenario.name,
        polygon=scenario.polygon,
        spacing=scenario.spacing,
        obstacles=scenario.obstacles,
        start=start_cost,
        end=end_cost,
    )


def build_mission_path(
    base_path: np.ndarray,
    obstacles: list[CircularObstacle],
    start: np.ndarray | None,
    end: np.ndarray | None,
) -> np.ndarray:
    base_path = np.asarray(base_path, dtype=float)
    if len(base_path) == 0:
        raise ValueError("base_path must contain at least one point.")

    mission: list[np.ndarray] = []
    if start is not None:
        start_point = np.asarray(start, dtype=float)
        mission.append(start_point)
        mission.extend(route_segment(start_point, base_path[0], obstacles))
    else:
        mission.append(base_path[0])

    for point in base_path[1:]:
        mission.append(np.asarray(point, dtype=float))

    if end is not None:
        end_point = np.asarray(end, dtype=float)
        mission.extend(route_segment(mission[-1], end_point, obstacles))

    return dedupe_path(mission)


def path_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    return float(np.linalg.norm(points[1:] - points[:-1], axis=1).sum())


def print_summary(result, mission_path: np.ndarray, scenario: ScenarioConfig, flight_mode: str) -> None:
    mission_end = resolve_mission_end(scenario)
    print(f"Scenario: {result.name}")
    if scenario.source_path is not None:
        print(f"Source: {scenario.source_path.resolve()}")
    if abs(scenario.geometry_scale - 1.0) > 1e-6:
        print(f"Geometry scale: x{scenario.geometry_scale:.4f} (normalized from source mask)")
    print(f"Flight path mode: {flight_mode}")
    print(f"Orientation: {result.orientation_deg:.2f} deg")
    print(f"Sweep lines: {result.sweep_lines} | Turns: {result.turns}")
    print(
        f"Coverage: {result.coverage_ratio * 100.0:.2f}% | "
        f"Overlap: {result.overlap_ratio * 100.0:.2f}%"
    )
    print(f"Planner cost: {result.cost:.2f}")
    print(f"Mission length: {path_length(mission_path):.2f}")
    if scenario.start is not None:
        print(f"Launch point: {scenario.start.tolist()}")
    if mission_end is not None:
        print(f"Landing point: {mission_end.tolist()}")
    print("Controls: space pause/resume, r reset, tab toggle reference, up/down change speed, esc quit.")


def run_pygame_simulation(
    result,
    mission_path: np.ndarray,
    scenario: ScenarioConfig,
    args: argparse.Namespace,
) -> None:
    try:
        import pygame
        from planning.Drawer import Drawer
    except ImportError as exc:
        raise SystemExit(
            "Pygame is not installed in the active environment. "
            "Run the simulator with an environment that has pygame."
        ) from exc

    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
    pygame.init()
    pygame.font.init()

    clock = pygame.time.Clock()
    uav = UAV(mission_path, speed=args.speed)
    mission_end = resolve_mission_end(scenario)
    drawer = Drawer(
        result=result,
        flight_path=mission_path,
        mission_start=scenario.start,
        mission_end=mission_end,
        window_size=(args.window_width, args.window_height),
    )

    reference_modes = ["none", "raw", "smooth"]
    reference_index = reference_modes.index(args.reference_path)
    paused = False
    running = True

    try:
        while running:
            dt = clock.tick(args.fps) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_SPACE:
                        paused = not paused
                    elif event.key == pygame.K_r:
                        uav.reset()
                        paused = False
                    elif event.key == pygame.K_TAB:
                        reference_index = (reference_index + 1) % len(reference_modes)
                    elif event.key == pygame.K_UP:
                        uav.set_speed(uav.speed + 20.0)
                    elif event.key == pygame.K_DOWN:
                        uav.set_speed(max(20.0, uav.speed - 20.0))

            if not paused:
                uav.update(dt)

            drawer.draw(
                uav=uav,
                paused=paused,
                fps=clock.get_fps(),
                reference_mode=reference_modes[reference_index],
                flight_path_mode=args.flight_path,
            )
    finally:
        pygame.quit()


def main() -> None:
    args = parse_args()

    if args.list_scenarios:
        print("Built-in paper scenarios:")
        for name in sorted(PAPER_SCENARIOS):
            print(f"- {name}")
        return

    if args.list_raw_masks:
        print_raw_mask_listing(args.raw_mask_dir)
        return

    scenario = resolve_scenario(args)
    result = build_planning_result(scenario)
    base_path = result.smooth_path if args.flight_path == "smooth" else result.path
    mission_path = build_mission_path(
        base_path=base_path,
        obstacles=result.obstacles,
        start=scenario.start,
        end=resolve_mission_end(scenario),
    )
    print_summary(result, mission_path, scenario, args.flight_path)
    run_pygame_simulation(result, mission_path, scenario, args)


if __name__ == "__main__":
    main()
