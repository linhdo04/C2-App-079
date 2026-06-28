from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

import numpy as np
import pygame


@dataclass(frozen=True)
class ViewTransform:
    scale: float
    min_corner: np.ndarray
    plot_origin: np.ndarray
    plot_size: np.ndarray

    def project_point(self, point: np.ndarray | Iterable[float]) -> tuple[int, int]:
        arr = np.asarray(point, dtype=float)
        mapped = (arr - self.min_corner) * self.scale + self.plot_origin
        return int(round(mapped[0])), int(round(mapped[1]))

    def project_points(self, points: np.ndarray | Iterable[Iterable[float]]) -> list[tuple[int, int]]:
        arr = np.asarray(list(points) if not isinstance(points, np.ndarray) else points, dtype=float)
        if arr.size == 0:
            return []
        mapped = (arr - self.min_corner) * self.scale + self.plot_origin
        return [tuple(np.rint(point).astype(int)) for point in mapped]

    def project_x(self, x_value: float) -> int:
        return int(round((float(x_value) - self.min_corner[0]) * self.scale + self.plot_origin[0]))

    def project_y(self, y_value: float) -> int:
        return int(round((float(y_value) - self.min_corner[1]) * self.scale + self.plot_origin[1]))

    @property
    def plot_rect(self) -> pygame.Rect:
        return pygame.Rect(
            int(round(self.plot_origin[0])),
            int(round(self.plot_origin[1])),
            int(round(self.plot_size[0])),
            int(round(self.plot_size[1])),
        )


class Drawer:
    class Color:
        WINDOW_BG = (10, 45, 93)
        FIGURE_BG = (248, 248, 248)
        FIGURE_BORDER = (231, 231, 231)
        AXES_BG = (252, 252, 252)
        AXES_BORDER = (120, 120, 120)
        GRID = (210, 210, 210)
        TICK = (30, 30, 30)
        TITLE = (35, 35, 35)
        ROI_FILL = (220, 239, 210, 230)
        ROI_BORDER = (53, 104, 89)
        OBSTACLE_FILL = (228, 196, 190, 205)
        OBSTACLE_BORDER = (240, 127, 0)
        RAW_PATH = (29, 53, 87)
        REFERENCE_PATH = (173, 181, 189)
        ANIMATED_PATH = (247, 127, 0)
        START = (42, 157, 143)
        END = (230, 57, 70)
        UAV = (255, 167, 38)
        PANEL_BG = (255, 255, 255, 226)
        PANEL_BORDER = (155, 155, 155)
        TEXT = (34, 34, 34)

    def __init__(
        self,
        result,
        flight_path: np.ndarray,
        mission_start: np.ndarray | None = None,
        mission_end: np.ndarray | None = None,
        window_size: tuple[int, int] = (1280, 900),
        margin: int = 28,
    ) -> None:
        self.result = result
        self.flight_path = np.asarray(flight_path, dtype=float)
        self.mission_start = None if mission_start is None else np.asarray(mission_start, dtype=float)
        self.mission_end = None if mission_end is None else np.asarray(mission_end, dtype=float)
        self.window = pygame.display.set_mode(window_size)
        pygame.display.set_caption(f"UAV Path Planning - {result.name}")

        self.title_font = pygame.font.SysFont("arial", 22)
        self.font = pygame.font.SysFont("arial", 16)
        self.small_font = pygame.font.SysFont("arial", 14)

        self.figure_rect = pygame.Rect(
            margin,
            margin,
            window_size[0] - margin * 2,
            window_size[1] - margin * 2,
        )
        self.transform = self._build_transform()
        self.screen_polygon = self.transform.project_points(result.polygon)
        self.screen_raw_path = self.transform.project_points(result.path)
        self.screen_reference_path = self.transform.project_points(result.smooth_path)
        self.screen_flight_path = self.transform.project_points(self.flight_path)
        self.start_point = self.transform.project_point(self.flight_path[0])
        self.end_point = self.transform.project_point(self.flight_path[-1])
        self.static_surface = pygame.Surface(window_size)
        self._draw_static_scene()

    def _build_transform(self) -> ViewTransform:
        inner_left = self.figure_rect.left + 68
        inner_top = self.figure_rect.top + 56
        inner_width = self.figure_rect.width - 92
        inner_height = self.figure_rect.height - 98
        available_size = np.array([inner_width, inner_height], dtype=float)

        cloud = [np.asarray(self.result.polygon, dtype=float)]
        for path in (self.result.path, self.result.smooth_path, self.flight_path):
            arr = np.asarray(path, dtype=float)
            if arr.size:
                cloud.append(arr)

        bounds_cloud: list[np.ndarray] = []
        for obstacle in self.result.obstacles:
            radius = float(obstacle.effective_radius)
            cx, cy = obstacle.center
            bounds_cloud.append(
                np.array(
                    [
                        [cx - radius, cy - radius],
                        [cx + radius, cy + radius],
                    ],
                    dtype=float,
                )
            )
        if bounds_cloud:
            cloud.append(np.vstack(bounds_cloud))

        all_points = np.vstack(cloud)
        min_corner = np.floor(all_points.min(axis=0))
        max_corner = np.ceil(all_points.max(axis=0))
        span = np.maximum(max_corner - min_corner, 1.0)
        scale = float(min(available_size[0] / span[0], available_size[1] / span[1]))
        plot_size = span * scale
        plot_origin = np.array(
            [
                inner_left + (available_size[0] - plot_size[0]) / 2.0,
                inner_top + (available_size[1] - plot_size[1]) / 2.0,
            ],
            dtype=float,
        )
        return ViewTransform(
            scale=scale,
            min_corner=min_corner,
            plot_origin=plot_origin,
            plot_size=plot_size,
        )

    def _draw_static_scene(self) -> None:
        self.static_surface.fill(self.Color.WINDOW_BG)
        pygame.draw.rect(self.static_surface, self.Color.FIGURE_BG, self.figure_rect)
        pygame.draw.rect(self.static_surface, self.Color.FIGURE_BORDER, self.figure_rect, width=1)

        plot_rect = self.transform.plot_rect
        pygame.draw.rect(self.static_surface, self.Color.AXES_BG, plot_rect)
        self._draw_grid_and_ticks(self.static_surface)
        self._draw_roi(self.static_surface)
        self._draw_obstacles(self.static_surface)
        self._draw_reference_paths(self.static_surface)
        pygame.draw.rect(self.static_surface, self.Color.AXES_BORDER, plot_rect, width=1)
        self._draw_title(self.static_surface)
        self._draw_legend(self.static_surface)
        self._draw_start_end_markers(self.static_surface)

    def _nice_tick_step(self, span: float) -> float:
        rough = max(float(span) / 8.0, 1.0)
        magnitude = 10.0 ** math.floor(math.log10(rough))
        normalized = rough / magnitude
        if normalized <= 1.0:
            nice = 1.0
        elif normalized <= 2.0:
            nice = 2.0
        elif normalized <= 2.5:
            nice = 2.5
        elif normalized <= 5.0:
            nice = 5.0
        else:
            nice = 10.0
        return nice * magnitude

    def _tick_values(self, lower: float, upper: float) -> list[float]:
        step = self._nice_tick_step(upper - lower)
        start = math.ceil(lower / step) * step
        values: list[float] = []
        current = start
        while current <= upper + step * 0.25:
            values.append(round(current, 6))
            current += step
        return values

    def _draw_grid_and_ticks(self, surface: pygame.Surface) -> None:
        plot_rect = self.transform.plot_rect
        min_corner = self.transform.min_corner
        max_corner = min_corner + self.transform.plot_size / self.transform.scale

        x_ticks = self._tick_values(float(min_corner[0]), float(max_corner[0]))
        y_ticks = self._tick_values(float(min_corner[1]), float(max_corner[1]))

        for x_value in x_ticks:
            screen_x = self.transform.project_x(x_value)
            pygame.draw.line(surface, self.Color.GRID, (screen_x, plot_rect.top), (screen_x, plot_rect.bottom), 1)
            label = self.small_font.render(str(int(round(x_value))), True, self.Color.TICK)
            label_rect = label.get_rect(midtop=(screen_x, plot_rect.bottom + 8))
            surface.blit(label, label_rect)

        for y_value in y_ticks:
            screen_y = self.transform.project_y(y_value)
            pygame.draw.line(surface, self.Color.GRID, (plot_rect.left, screen_y), (plot_rect.right, screen_y), 1)
            label = self.small_font.render(str(int(round(y_value))), True, self.Color.TICK)
            label_rect = label.get_rect(midright=(plot_rect.left - 8, screen_y))
            surface.blit(label, label_rect)

    def _draw_roi(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        pygame.draw.polygon(overlay, self.Color.ROI_FILL, self.screen_polygon)
        pygame.draw.polygon(overlay, self.Color.ROI_BORDER, self.screen_polygon, width=2)
        surface.blit(overlay, (0, 0))

    def _draw_obstacles(self, surface: pygame.Surface) -> None:
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for obstacle in self.result.obstacles:
            center = self.transform.project_point(obstacle.center)
            radius = max(2, int(round(float(obstacle.effective_radius) * self.transform.scale)))
            pygame.draw.circle(overlay, self.Color.OBSTACLE_FILL, center, radius)
            pygame.draw.circle(overlay, self.Color.OBSTACLE_BORDER, center, radius, width=2)
        surface.blit(overlay, (0, 0))

    def _draw_polyline(
        self,
        surface: pygame.Surface,
        points: list[tuple[int, int]],
        color: tuple[int, int, int],
        width: int,
    ) -> None:
        if len(points) >= 2:
            pygame.draw.lines(surface, color, False, points, width)

    def _draw_dashed_polyline(
        self,
        surface: pygame.Surface,
        points: list[tuple[int, int]],
        color: tuple[int, int, int],
        width: int,
        dash_length: float = 8.0,
        gap_length: float = 6.0,
    ) -> None:
        if len(points) < 2:
            return

        pattern = dash_length + gap_length
        for start, end in zip(points[:-1], points[1:]):
            start_arr = np.asarray(start, dtype=float)
            end_arr = np.asarray(end, dtype=float)
            segment = end_arr - start_arr
            length = float(np.linalg.norm(segment))
            if length <= 1e-6:
                continue
            direction = segment / length
            travelled = 0.0
            while travelled < length:
                dash_start = start_arr + direction * travelled
                dash_end = start_arr + direction * min(travelled + dash_length, length)
                pygame.draw.line(
                    surface,
                    color,
                    tuple(np.rint(dash_start).astype(int)),
                    tuple(np.rint(dash_end).astype(int)),
                    width,
                )
                travelled += pattern

    def _draw_reference_paths(self, surface: pygame.Surface) -> None:
        self._draw_polyline(surface, self.screen_raw_path, self.Color.RAW_PATH, 2)
        self._draw_dashed_polyline(surface, self.screen_reference_path, self.Color.REFERENCE_PATH, 2)

    def _draw_title(self, surface: pygame.Surface) -> None:
        title_surface = self.title_font.render(self.result.name, True, self.Color.TITLE)
        title_rect = title_surface.get_rect(
            center=(self.figure_rect.centerx, self.figure_rect.top + 22)
        )
        surface.blit(title_surface, title_rect)

    def _draw_start_end_markers(self, surface: pygame.Surface) -> None:
        pygame.draw.circle(surface, self.Color.START, self.start_point, 5)
        pygame.draw.circle(surface, self.Color.END, self.end_point, 5)

    def _draw_legend(self, surface: pygame.Surface) -> None:
        items = [
            ("patch", self.Color.ROI_FILL[:3], "ROI"),
            ("patch", self.Color.OBSTACLE_FILL[:3], "Obstacle"),
            ("line", self.Color.RAW_PATH, "Raw path"),
            ("dash", self.Color.REFERENCE_PATH, "Reference path"),
            ("dot", self.Color.START, "Start"),
            ("dot", self.Color.END, "End"),
            ("line", self.Color.ANIMATED_PATH, "Animated path"),
            ("dot", self.Color.UAV, "UAV"),
        ]

        padding = 10
        row_height = 19
        width = 170
        height = padding * 2 + row_height * len(items)
        plot_rect = self.transform.plot_rect
        legend_rect = pygame.Rect(
            plot_rect.right - width - 6,
            plot_rect.bottom - height - 6,
            width,
            height,
        )

        legend = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(legend, self.Color.PANEL_BG, legend.get_rect(), border_radius=6)
        pygame.draw.rect(legend, self.Color.PANEL_BORDER, legend.get_rect(), width=1, border_radius=6)

        for index, (kind, color, label) in enumerate(items):
            y = padding + index * row_height + row_height // 2
            if kind == "patch":
                pygame.draw.rect(legend, color, (12, y - 5, 18, 10))
                pygame.draw.rect(legend, self.Color.PANEL_BORDER, (12, y - 5, 18, 10), width=1)
            elif kind == "line":
                pygame.draw.line(legend, color, (12, y), (32, y), 3)
            elif kind == "dash":
                pygame.draw.line(legend, color, (12, y), (20, y), 2)
                pygame.draw.line(legend, color, (24, y), (32, y), 2)
            elif kind == "dot":
                pygame.draw.circle(legend, color, (22, y), 4)
            text_surface = self.small_font.render(label, True, self.Color.TEXT)
            legend.blit(text_surface, (42, y - text_surface.get_height() // 2))

        surface.blit(legend, legend_rect.topleft)

    def _draw_metrics_panel(self, surface: pygame.Surface, progress_ratio: float) -> None:
        lines = [
            f"angle={self.result.orientation_deg:.2f} deg",
            f"sweeps={self.result.sweep_lines}",
            f"turns={self.result.turns}",
            f"coverage={self.result.coverage_ratio * 100.0:.2f}%",
            f"overlap={self.result.overlap_ratio * 100.0:.2f}%",
            f"progress={progress_ratio * 100.0:.1f}%",
        ]
        padding = 8
        line_height = 17
        width = 142
        height = padding * 2 + line_height * len(lines)
        plot_rect = self.transform.plot_rect
        panel_rect = pygame.Rect(plot_rect.left + 8, plot_rect.top + 8, width, height)

        panel = pygame.Surface((width, height), pygame.SRCALPHA)
        pygame.draw.rect(panel, self.Color.PANEL_BG, panel.get_rect())
        pygame.draw.rect(panel, self.Color.PANEL_BORDER, panel.get_rect(), width=1)
        for index, line in enumerate(lines):
            text_surface = self.small_font.render(line, True, self.Color.TEXT)
            panel.blit(text_surface, (padding, padding + index * line_height))
        surface.blit(panel, panel_rect.topleft)

    def _draw_uav(self, surface: pygame.Surface, position: np.ndarray) -> None:
        point = self.transform.project_point(position)
        pygame.draw.circle(surface, self.Color.UAV, point, 6)
        pygame.draw.circle(surface, self.Color.TEXT, point, 6, width=1)

    def draw(
        self,
        uav,
        paused: bool,
        fps: float,
        reference_mode: str = "raw",
        flight_path_mode: str = "smooth",
    ) -> None:
        del paused, fps, reference_mode, flight_path_mode

        self.window.blit(self.static_surface, (0, 0))
        animated_points = self.transform.project_points(uav.trail)
        self._draw_polyline(self.window, animated_points, self.Color.ANIMATED_PATH, 3)
        self._draw_uav(self.window, uav.position)
        self._draw_metrics_panel(self.window, uav.progress_ratio)
        pygame.display.flip()
