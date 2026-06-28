from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np


STATE_EMPTY = 0
STATE_ROI = 1
STATE_OBSTACLE = 2


MODE_NAMES = [
    "Outside",
    "ROI",
    "Obstacle",
    "Launch",
    "Landing",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive pygame editor for UAV path-planning scenarios."
    )
    parser.add_argument("--rows", type=int, default=28)
    parser.add_argument("--cols", type=int, default=36)
    parser.add_argument("--cell-size", type=int, default=24)
    parser.add_argument("--spacing", type=float, default=28.0)
    parser.add_argument("--safety-margin", type=float, default=8.0)
    parser.add_argument("--output", type=Path, default=Path("generated_scenario.json"))
    parser.add_argument("--name", default="custom_path_planning_case")
    return parser.parse_args()


def require_pygame():
    try:
        import pygame
    except ImportError as exc:
        raise SystemExit(
            "Pygame is not installed in the active environment. "
            "Run gen_test.py with an environment that has pygame."
        ) from exc
    return pygame


def draw_brush(grid: np.ndarray, row: int, col: int, state: int) -> None:
    if 0 <= row < grid.shape[0] and 0 <= col < grid.shape[1]:
        grid[row, col] = state


def build_masks(grid: np.ndarray, cell_size: int) -> tuple[np.ndarray, np.ndarray]:
    height = grid.shape[0] * cell_size
    width = grid.shape[1] * cell_size
    roi_mask = np.zeros((height, width), dtype=np.uint8)
    obstacle_mask = np.zeros((height, width), dtype=np.uint8)

    for row in range(grid.shape[0]):
        for col in range(grid.shape[1]):
            y0 = row * cell_size
            y1 = y0 + cell_size
            x0 = col * cell_size
            x1 = x0 + cell_size

            if grid[row, col] == STATE_ROI:
                roi_mask[y0:y1, x0:x1] = 255
            elif grid[row, col] == STATE_OBSTACLE:
                roi_mask[y0:y1, x0:x1] = 255
                obstacle_mask[y0:y1, x0:x1] = 255

    return roi_mask, obstacle_mask


def contour_to_polygon(contour: np.ndarray) -> list[list[float]]:
    perimeter = cv2.arcLength(contour, True)
    epsilon = max(2.0, 0.005 * perimeter)
    approx = cv2.approxPolyDP(contour, epsilon, True)
    polygon = approx[:, 0, :].astype(float)
    if len(polygon) < 3:
        polygon = contour[:, 0, :].astype(float)
    return [[float(point[0]), float(point[1])] for point in polygon]


def cell_to_world(cell: tuple[int, int] | None, cell_size: int) -> list[float] | None:
    if cell is None:
        return None
    row, col = cell
    return [float(col * cell_size + cell_size / 2.0), float(row * cell_size + cell_size / 2.0)]


def export_scenario(
    grid: np.ndarray,
    spacing: float,
    cell_size: int,
    output_path: Path,
    name: str,
    safety_margin: float,
    launch_cell: tuple[int, int] | None,
    landing_cell: tuple[int, int] | None,
) -> None:
    roi_mask, obstacle_mask = build_masks(grid, cell_size)
    contours, _ = cv2.findContours(roi_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("The scenario must contain at least one ROI cell.")

    main_contour = max(contours, key=cv2.contourArea)
    polygon = contour_to_polygon(main_contour)

    obstacles = []
    obstacle_contours, _ = cv2.findContours(obstacle_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum_area = max(1.0, 0.35 * cell_size * cell_size)
    for contour in obstacle_contours:
        area = cv2.contourArea(contour)
        if area < minimum_area:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        obstacles.append(
            {
                "center": [float(x), float(y)],
                "radius": float(radius),
                "safety_margin": float(safety_margin),
            }
        )

    payload = {
        "name": name,
        "spacing": float(spacing),
        "polygon": polygon,
        "obstacles": obstacles,
        "start": cell_to_world(launch_cell, cell_size),
        "end": cell_to_world(landing_cell, cell_size),
        "meta": {
            "rows": int(grid.shape[0]),
            "cols": int(grid.shape[1]),
            "cell_size": int(cell_size),
        },
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_editor(args: argparse.Namespace) -> None:
    pygame = require_pygame()
    pygame.init()
    pygame.font.init()

    hud_height = 108
    width = args.cols * args.cell_size
    height = args.rows * args.cell_size + hud_height
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Scenario Editor - UAV Path Planning")
    font = pygame.font.SysFont("consolas", 18)
    small_font = pygame.font.SysFont("consolas", 15)
    clock = pygame.time.Clock()

    colors = {
        STATE_EMPTY: (74, 84, 92),
        STATE_ROI: (242, 244, 240),
        STATE_OBSTACLE: (187, 61, 70),
    }
    text_color = (22, 27, 31)
    hud_color = (247, 248, 249)
    hud_border = (204, 208, 214)
    launch_color = (22, 149, 118)
    landing_color = (52, 89, 149)

    grid = np.zeros((args.rows, args.cols), dtype=np.int8)
    current_mode = 1
    launch_cell: tuple[int, int] | None = None
    landing_cell: tuple[int, int] | None = None
    spacing = float(args.spacing)
    left_down = False
    right_down = False
    running = True

    def erase_at(row: int, col: int) -> None:
        nonlocal launch_cell, landing_cell
        if launch_cell == (row, col):
            launch_cell = None
        if landing_cell == (row, col):
            landing_cell = None
        grid[row, col] = STATE_EMPTY

    def apply_current_tool(row: int, col: int) -> None:
        nonlocal launch_cell, landing_cell
        if current_mode == 0:
            erase_at(row, col)
        elif current_mode == 1:
            draw_brush(grid, row, col, STATE_ROI)
        elif current_mode == 2:
            draw_brush(grid, row, col, STATE_OBSTACLE)
        elif current_mode == 3:
            launch_cell = (row, col)
        elif current_mode == 4:
            landing_cell = (row, col)

    try:
        while running:
            dt = clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_TAB:
                        current_mode = (current_mode + 1) % len(MODE_NAMES)
                    elif event.key == pygame.K_a:
                        spacing = max(4.0, spacing - 2.0)
                    elif event.key == pygame.K_s:
                        spacing += 2.0
                    elif event.key == pygame.K_c:
                        grid.fill(STATE_EMPTY)
                        launch_cell = None
                        landing_cell = None
                    elif event.key == pygame.K_RETURN:
                        export_scenario(
                            grid=grid,
                            spacing=spacing,
                            cell_size=args.cell_size,
                            output_path=args.output,
                            name=args.name,
                            safety_margin=args.safety_margin,
                            launch_cell=launch_cell,
                            landing_cell=landing_cell,
                        )
                        print(f"Saved scenario to: {args.output.resolve()}")
                        running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if event.button == 1:
                        left_down = True
                    elif event.button == 3:
                        right_down = True
                elif event.type == pygame.MOUSEBUTTONUP:
                    if event.button == 1:
                        left_down = False
                    elif event.button == 3:
                        right_down = False

            mouse_x, mouse_y = pygame.mouse.get_pos()
            in_grid = mouse_y >= hud_height
            if in_grid:
                col = mouse_x // args.cell_size
                row = (mouse_y - hud_height) // args.cell_size
                if 0 <= row < args.rows and 0 <= col < args.cols:
                    if left_down:
                        apply_current_tool(row, col)
                    elif right_down:
                        erase_at(row, col)

            screen.fill((237, 240, 242))
            pygame.draw.rect(screen, hud_color, (0, 0, width, hud_height))
            pygame.draw.line(screen, hud_border, (0, hud_height - 1), (width, hud_height - 1), 2)

            info_lines = [
                f"Mode: {MODE_NAMES[current_mode]}",
                f"Spacing: {spacing:.1f} px",
                f"Output: {args.output.name}",
                "TAB change tool | A/S change spacing | C clear | ENTER save | ESC quit",
                "Left click to draw, right click to erase.",
            ]
            for index, line in enumerate(info_lines):
                renderer = font if index < 3 else small_font
                text_surface = renderer.render(line, True, text_color)
                screen.blit(text_surface, (16, 12 + index * 18))

            for row in range(args.rows):
                for col in range(args.cols):
                    x = col * args.cell_size
                    y = hud_height + row * args.cell_size
                    rect = pygame.Rect(x, y, args.cell_size, args.cell_size)
                    pygame.draw.rect(screen, colors[int(grid[row, col])], rect)
                    pygame.draw.rect(screen, (118, 124, 129), rect, width=1)

                    if launch_cell == (row, col):
                        pygame.draw.circle(screen, launch_color, rect.center, max(5, args.cell_size // 4))
                    if landing_cell == (row, col):
                        pygame.draw.circle(screen, landing_color, rect.center, max(5, args.cell_size // 4))

            fps_surface = small_font.render(f"FPS: {clock.get_fps():4.1f}", True, text_color)
            screen.blit(fps_surface, (width - 110, 12))
            dt_surface = small_font.render(f"dt: {dt:3d} ms", True, text_color)
            screen.blit(dt_surface, (width - 110, 32))
            pygame.display.flip()
    finally:
        pygame.quit()


def main() -> None:
    args = parse_args()
    run_editor(args)


if __name__ == "__main__":
    main()
