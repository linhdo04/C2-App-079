from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import cv2
import numpy as np
from scipy.interpolate import PchipInterpolator

EPS = 1e-6


@dataclass(frozen=True)
class CircularObstacle:
    center: tuple[float, float]
    radius: float
    safety_margin: float = 0.0

    @property
    def effective_radius(self) -> float:
        return float(self.radius + self.safety_margin)


@dataclass
class PlanningResult:
    name: str
    polygon: np.ndarray
    spacing: float
    path: np.ndarray
    smooth_path: np.ndarray
    obstacles: list[CircularObstacle]
    orientation_deg: float
    cost: float
    sweep_lines: int
    turns: int
    coverage_ratio: float
    overlap_ratio: float


def cross2d(a: np.ndarray, b: np.ndarray) -> float:
    return float(a[0] * b[1] - a[1] * b[0])


def as_points(points: Sequence[Sequence[float]]) -> np.ndarray:
    arr = np.asarray(points, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError("Expected an array of shape (n, 2).")
    return arr


def polygon_area(points: np.ndarray) -> float:
    x = points[:, 0]
    y = points[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def ensure_ccw(points: np.ndarray) -> np.ndarray:
    return points if polygon_area(points) >= 0 else points[::-1].copy()


def rotate_points(points: np.ndarray, angle: float, origin: np.ndarray) -> np.ndarray:
    c = math.cos(angle)
    s = math.sin(angle)
    rot = np.array([[c, -s], [s, c]], dtype=float)
    shifted = points - origin
    return shifted @ rot.T + origin


def rotate_obstacles(
    obstacles: Iterable[CircularObstacle], angle: float, origin: np.ndarray
) -> list[CircularObstacle]:
    rotated: list[CircularObstacle] = []
    for obstacle in obstacles:
        center = rotate_points(np.asarray([obstacle.center], dtype=float), angle, origin)[0]
        rotated.append(
            CircularObstacle(
                center=(float(center[0]), float(center[1])),
                radius=obstacle.radius,
                safety_margin=obstacle.safety_margin,
            )
        )
    return rotated


def unique_edge_angles(points: np.ndarray) -> list[float]:
    angles: list[float] = []
    for idx in range(len(points)):
        nxt = (idx + 1) % len(points)
        edge = points[nxt] - points[idx]
        if np.linalg.norm(edge) <= EPS:
            continue
        angle = math.atan2(edge[1], edge[0]) % math.pi
        if all(abs(math.sin(angle - seen)) > 1e-4 for seen in angles):
            angles.append(angle)
    if not angles:
        raise ValueError("Polygon has no valid edges.")
    return angles


def scanline_intervals(points: np.ndarray, y: float) -> list[tuple[float, float]]:
    hits: list[float] = []
    total = len(points)
    for idx in range(total):
        p1 = points[idx]
        p2 = points[(idx + 1) % total]
        y1, y2 = p1[1], p2[1]
        if abs(y1 - y2) <= EPS:
            continue
        if (y1 <= y < y2) or (y2 <= y < y1):
            t = (y - y1) / (y2 - y1)
            x = p1[0] + t * (p2[0] - p1[0])
            hits.append(float(x))
    hits.sort()
    intervals: list[tuple[float, float]] = []
    for idx in range(0, len(hits) - 1, 2):
        left = hits[idx]
        right = hits[idx + 1]
        if right - left > EPS:
            intervals.append((left, right))
    return intervals


def subtract_obstacles_from_intervals(
    intervals: list[tuple[float, float]],
    y: float,
    obstacles: Sequence[CircularObstacle],
) -> list[tuple[float, float]]:
    remaining = list(intervals)
    for obstacle in obstacles:
        cx, cy = obstacle.center
        radius = obstacle.effective_radius
        dy = y - cy
        if abs(dy) >= radius - EPS:
            continue
        half = math.sqrt(max(radius * radius - dy * dy, 0.0))
        block_left = cx - half
        block_right = cx + half
        updated: list[tuple[float, float]] = []
        for left, right in remaining:
            if right <= block_left + EPS or left >= block_right - EPS:
                updated.append((left, right))
                continue
            if left < block_left - EPS:
                updated.append((left, block_left))
            if block_right < right - EPS:
                updated.append((block_right, right))
        remaining = updated
    return remaining


def build_sweep_rows(
    points: np.ndarray,
    spacing: float,
    obstacles: Sequence[CircularObstacle],
) -> list[dict[str, object]]:
    ymin = float(points[:, 1].min())
    ymax = float(points[:, 1].max())
    height = ymax - ymin
    if height <= spacing:
        y_values = [0.5 * (ymin + ymax)]
    else:
        y_values = list(np.arange(ymin + spacing / 2.0, ymax, spacing))
        if not y_values:
            y_values = [0.5 * (ymin + ymax)]

    rows: list[dict[str, object]] = []
    for y in y_values:
        y_clamped = min(max(y, ymin + 1e-3), ymax - 1e-3)
        intervals = scanline_intervals(points, y_clamped)
        intervals = subtract_obstacles_from_intervals(intervals, y_clamped, obstacles)
        if intervals:
            rows.append({"y": float(y_clamped), "intervals": intervals})
    return rows


def segment_circle_hit(
    start: np.ndarray, end: np.ndarray, obstacle: CircularObstacle
) -> tuple[float, float] | None:
    direction = end - start
    a = float(np.dot(direction, direction))
    if a <= EPS:
        return None
    center = np.asarray(obstacle.center, dtype=float)
    f = start - center
    b = 2.0 * float(np.dot(f, direction))
    c = float(np.dot(f, f) - obstacle.effective_radius ** 2)
    discriminant = b * b - 4.0 * a * c
    if discriminant <= EPS:
        return None
    sqrt_disc = math.sqrt(discriminant)
    t1 = (-b - sqrt_disc) / (2.0 * a)
    t2 = (-b + sqrt_disc) / (2.0 * a)
    enter = max(min(t1, t2), 0.0)
    leave = min(max(t1, t2), 1.0)
    if leave - enter <= 1e-4:
        return None
    if leave <= 1e-4 or enter >= 1.0 - 1e-4:
        return None
    return enter, leave


def arc_candidates(theta_start: float, theta_end: float, samples: int) -> tuple[np.ndarray, np.ndarray]:
    ccw_end = theta_end
    if ccw_end < theta_start:
        ccw_end += 2.0 * math.pi
    cw_end = theta_end
    if cw_end > theta_start:
        cw_end -= 2.0 * math.pi
    ccw = np.linspace(theta_start, ccw_end, samples)
    cw = np.linspace(theta_start, cw_end, samples)
    return ccw, cw


def obstacle_arc(
    enter: np.ndarray,
    leave: np.ndarray,
    obstacle: CircularObstacle,
    segment_start: np.ndarray,
    segment_end: np.ndarray,
    preferred_side: float,
    samples: int = 16,
) -> np.ndarray:
    center = np.asarray(obstacle.center, dtype=float)
    radius = obstacle.effective_radius
    theta_start = math.atan2(enter[1] - center[1], enter[0] - center[0])
    theta_end = math.atan2(leave[1] - center[1], leave[0] - center[0])
    ccw, cw = arc_candidates(theta_start, theta_end, samples)

    def build_path(angles: np.ndarray) -> np.ndarray:
        return np.column_stack(
            [center[0] + radius * np.cos(angles), center[1] + radius * np.sin(angles)]
        )

    def side_score(path: np.ndarray) -> float:
        direction = segment_end - segment_start
        values = [cross2d(direction, point - segment_start) for point in path[1:-1]]
        if not values:
            return 0.0
        return float(np.mean(np.sign(values)))

    ccw_path = build_path(ccw)
    cw_path = build_path(cw)
    ccw_score = abs(side_score(ccw_path) - preferred_side)
    cw_score = abs(side_score(cw_path) - preferred_side)
    if ccw_score < cw_score:
        return ccw_path
    if cw_score < ccw_score:
        return cw_path
    return ccw_path if len(ccw) <= len(cw) else cw_path


def route_segment(
    start: np.ndarray,
    end: np.ndarray,
    obstacles: Sequence[CircularObstacle],
    depth: int = 0,
) -> list[np.ndarray]:
    if depth > 12 or np.linalg.norm(end - start) <= EPS:
        return [end]

    nearest: tuple[CircularObstacle, float, float] | None = None
    for obstacle in obstacles:
        hit = segment_circle_hit(start, end, obstacle)
        if hit is None:
            continue
        if nearest is None or hit[0] < nearest[1]:
            nearest = (obstacle, hit[0], hit[1])

    if nearest is None:
        return [end]

    obstacle, t_enter, t_leave = nearest
    direction = end - start
    enter = start + direction * t_enter
    leave = start + direction * t_leave
    signed = cross2d(direction, np.asarray(obstacle.center, dtype=float) - start)
    preferred_side = 1.0 if signed >= 0.0 else -1.0
    arc = obstacle_arc(enter, leave, obstacle, start, end, preferred_side)

    routed: list[np.ndarray] = []
    if np.linalg.norm(enter - start) > EPS:
        routed.append(enter)
    for point in arc[1:]:
        if not routed or np.linalg.norm(point - routed[-1]) > EPS:
            routed.append(point)

    norm = np.linalg.norm(direction)
    if norm > EPS:
        shifted_leave = leave + direction / norm * 1e-3
    else:
        shifted_leave = leave
    tail = route_segment(shifted_leave, end, obstacles, depth + 1)
    for point in tail:
        if np.linalg.norm(point - routed[-1]) > EPS:
            routed.append(point)
    return routed


def dedupe_path(points: Sequence[np.ndarray]) -> np.ndarray:
    filtered: list[np.ndarray] = []
    for point in points:
        arr = np.asarray(point, dtype=float)
        if not filtered or np.linalg.norm(arr - filtered[-1]) > 1e-4:
            filtered.append(arr)
    return np.asarray(filtered, dtype=float)


def build_snake_path(
    rows: Sequence[dict[str, object]],
    first_direction: int,
    obstacles: Sequence[CircularObstacle],
) -> np.ndarray:
    direction = first_direction
    path: list[np.ndarray] = []

    for row in rows:
        y = float(row["y"])
        intervals = list(row["intervals"])
        ordered = intervals if direction > 0 else list(reversed(intervals))
        row_targets: list[np.ndarray] = []
        for left, right in ordered:
            start_x, end_x = (left, right) if direction > 0 else (right, left)
            row_targets.append(np.array([start_x, y], dtype=float))
            row_targets.append(np.array([end_x, y], dtype=float))

        if not row_targets:
            direction *= -1
            continue

        if not path:
            path.append(row_targets[0])
        elif np.linalg.norm(path[-1] - row_targets[0]) > EPS:
            path.extend(route_segment(path[-1], row_targets[0], obstacles))

        for target in row_targets[1:]:
            if np.linalg.norm(path[-1] - target) > EPS:
                path.extend(route_segment(path[-1], target, obstacles))

        direction *= -1

    return dedupe_path(path)


def path_length(points: np.ndarray) -> float:
    if len(points) < 2:
        return 0.0
    diffs = points[1:] - points[:-1]
    return float(np.linalg.norm(diffs, axis=1).sum())


def count_turns(points: np.ndarray, threshold_deg: float = 10.0) -> int:
    if len(points) < 3:
        return 0
    threshold = math.radians(threshold_deg)
    turns = 0
    for idx in range(1, len(points) - 1):
        v1 = points[idx] - points[idx - 1]
        v2 = points[idx + 1] - points[idx]
        n1 = np.linalg.norm(v1)
        n2 = np.linalg.norm(v2)
        if n1 <= EPS or n2 <= EPS:
            continue
        dot = float(np.clip(np.dot(v1, v2) / (n1 * n2), -1.0, 1.0))
        angle = math.acos(dot)
        if angle >= threshold:
            turns += 1
    return turns


def smooth_path(points: np.ndarray, density: int = 10) -> np.ndarray:
    points = dedupe_path(points)
    if len(points) < 4:
        return points
    steps = np.linalg.norm(points[1:] - points[:-1], axis=1)
    cumulative = np.concatenate([[0.0], np.cumsum(steps)])
    if cumulative[-1] <= EPS:
        return points
    try:
        parameter = cumulative / cumulative[-1]
        interp_x = PchipInterpolator(parameter, points[:, 0])
        interp_y = PchipInterpolator(parameter, points[:, 1])
        sample_count = max(len(points) * density, 200)
        samples = np.linspace(0.0, 1.0, sample_count)
        x_new = interp_x(samples)
        y_new = interp_y(samples)
        return np.column_stack([x_new, y_new])
    except ValueError:
        return points


def rasterize_coverage(
    polygon: np.ndarray,
    path: np.ndarray,
    spacing: float,
    obstacles: Sequence[CircularObstacle],
    scale: int = 4,
    max_pixels: int = 4_000_000,
) -> tuple[float, float]:
    max_radius = max((obstacle.effective_radius for obstacle in obstacles), default=0.0)
    all_points = polygon if len(path) == 0 else np.vstack([polygon, path])
    margin = spacing + max_radius + 8.0
    min_corner = np.floor(all_points.min(axis=0) - margin)
    max_corner = np.ceil(all_points.max(axis=0) + margin)
    raw_width = max((max_corner[0] - min_corner[0]) * scale, 10.0)
    raw_height = max((max_corner[1] - min_corner[1]) * scale, 10.0)
    raster_scale = float(scale)
    if raw_width * raw_height > max_pixels:
        shrink = math.sqrt(max_pixels / (raw_width * raw_height))
        raster_scale = max(0.5, raster_scale * shrink)
        raw_width = max((max_corner[0] - min_corner[0]) * raster_scale, 10.0)
        raw_height = max((max_corner[1] - min_corner[1]) * raster_scale, 10.0)

    width = int(raw_width)
    height = int(raw_height)

    def to_image(points_like: np.ndarray) -> np.ndarray:
        points_arr = np.asarray(points_like, dtype=float)
        result = np.empty_like(points_arr)
        result[:, 0] = (points_arr[:, 0] - min_corner[0]) * raster_scale
        result[:, 1] = (max_corner[1] - points_arr[:, 1]) * raster_scale
        return np.rint(result).astype(np.int32)

    roi = np.zeros((height + 1, width + 1), dtype=np.uint8)
    cv2.fillPoly(roi, [to_image(polygon)], 255)
    for obstacle in obstacles:
        center = to_image(np.asarray([obstacle.center], dtype=float))[0]
        radius = max(1, int(round(obstacle.effective_radius * raster_scale)))
        cv2.circle(roi, tuple(center), radius, 0, -1)

    covered = np.zeros_like(roi)
    if len(path) >= 2:
        thickness = max(1, int(round(spacing * raster_scale)))
        cv2.polylines(covered, [to_image(path)], False, 255, thickness=thickness, lineType=cv2.LINE_AA)

    roi_mask = roi > 0
    covered_mask = covered > 0
    inside_coverage = roi_mask & covered_mask
    outside_coverage = (~roi_mask) & covered_mask
    coverage_ratio = float(inside_coverage.sum() / max(roi_mask.sum(), 1))
    overlap_ratio = float(outside_coverage.sum() / max(covered_mask.sum(), 1))
    return coverage_ratio, overlap_ratio


def build_label_binary(mask: np.ndarray, labels: Sequence[int]) -> np.ndarray:
    if mask.ndim != 2:
        raise ValueError("Mask must be a single-channel array.")
    return np.isin(mask, labels).astype(np.uint8) * 255


def extract_primary_contour(binary_mask: np.ndarray) -> np.ndarray:
    if binary_mask.ndim != 2:
        raise ValueError("Binary mask must be a single-channel array.")
    contours, _ = cv2.findContours(binary_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError("No ROI contour was found for the requested labels.")
    return max(contours, key=cv2.contourArea)


def contour_to_polygon(
    contour: np.ndarray,
    approx_epsilon_ratio: float = 0.002,
    use_convex_hull: bool = False,
) -> np.ndarray:
    working_contour = cv2.convexHull(contour) if use_convex_hull else contour
    perimeter = cv2.arcLength(working_contour, True)
    epsilon = max(1.5, float(perimeter * approx_epsilon_ratio))
    approx = cv2.approxPolyDP(working_contour, epsilon, True)
    polygon_contour = approx if len(approx) >= 3 else working_contour
    return ensure_ccw(polygon_contour[:, 0, :].astype(float))


def plan_rcpp(
    name: str,
    polygon: Sequence[Sequence[float]],
    spacing: float,
    obstacles: Sequence[CircularObstacle] | None = None,
    start: Sequence[float] | None = None,
    end: Sequence[float] | None = None,
) -> PlanningResult:
    polygon_arr = ensure_ccw(as_points(polygon))
    obstacle_list = list(obstacles or [])
    start_point = None if start is None else np.asarray(start, dtype=float)
    end_point = None if end is None else np.asarray(end, dtype=float)
    origin = polygon_arr.mean(axis=0)

    best: dict[str, object] | None = None
    for angle in unique_edge_angles(polygon_arr):
        rotated_polygon = rotate_points(polygon_arr, -angle, origin)
        rotated_obstacles = rotate_obstacles(obstacle_list, -angle, origin)
        rows = build_sweep_rows(rotated_polygon, spacing, rotated_obstacles)
        if not rows:
            continue

        for row_order in (1, -1):
            ordered_rows = rows if row_order > 0 else list(reversed(rows))
            for first_direction in (1, -1):
                local_path = build_snake_path(ordered_rows, first_direction, rotated_obstacles)
                if len(local_path) < 2:
                    continue
                world_path = rotate_points(local_path, angle, origin)
                for reverse in (False, True):
                    candidate = world_path[::-1].copy() if reverse else world_path.copy()
                    cost = path_length(candidate)
                    if start_point is not None and end_point is not None:
                        cost += float(np.linalg.norm(candidate[0] - start_point))
                        cost += float(np.linalg.norm(candidate[-1] - end_point))
                    if best is None or cost < float(best["cost"]):
                        best = {
                            "path": candidate,
                            "cost": cost,
                            "angle": angle,
                            "rows": len(rows),
                        }

    if best is None:
        raise RuntimeError("Could not generate a valid coverage path.")

    raw_path = dedupe_path(best["path"])
    smooth = smooth_path(raw_path)
    coverage_ratio, overlap_ratio = rasterize_coverage(
        polygon_arr,
        raw_path,
        spacing,
        obstacle_list,
    )

    return PlanningResult(
        name=name,
        polygon=polygon_arr,
        spacing=float(spacing),
        path=raw_path,
        smooth_path=smooth,
        obstacles=obstacle_list,
        orientation_deg=float(math.degrees(float(best["angle"])) % 180.0),
        cost=float(best["cost"]),
        sweep_lines=int(best["rows"]),
        turns=count_turns(raw_path),
        coverage_ratio=coverage_ratio,
        overlap_ratio=overlap_ratio,
    )


def extract_roi_from_mask(
    mask: np.ndarray,
    roi_labels: Sequence[int],
    obstacle_labels: Sequence[int] | None = None,
    min_obstacle_area: float = 2000.0,
    safety_margin: float = 8.0,
    approx_epsilon_ratio: float = 0.002,
    use_convex_hull: bool = False,
) -> tuple[np.ndarray, list[CircularObstacle]]:
    if mask.ndim != 2:
        raise ValueError("Mask must be a single-channel array.")

    roi_binary = build_label_binary(mask, roi_labels)
    main_contour = extract_primary_contour(roi_binary)
    polygon = contour_to_polygon(
        main_contour,
        approx_epsilon_ratio=approx_epsilon_ratio,
        use_convex_hull=use_convex_hull,
    )

    obstacles: list[CircularObstacle] = []
    if obstacle_labels:
        obstacle_binary = build_label_binary(mask, obstacle_labels)
        obstacle_contours, _ = cv2.findContours(
            obstacle_binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        for contour in obstacle_contours:
            area = cv2.contourArea(contour)
            if area < min_obstacle_area:
                continue
            (x, y), radius = cv2.minEnclosingCircle(contour)
            if cv2.pointPolygonTest(main_contour, (float(x), float(y)), False) >= 0:
                obstacles.append(
                    CircularObstacle(
                        center=(float(x), float(y)),
                        radius=float(radius),
                        safety_margin=float(safety_margin),
                    )
                )

    return polygon, obstacles
