from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grid-based pygame viewer/editor for binary ROI masks."
    )
    parser.add_argument(
        "--mask-path",
        type=Path,
        help="Optional source mask. Can be a raw landcover mask or a binary mask.",
    )
    parser.add_argument(
        "--roi-labels",
        default="auto",
        help=(
            "ROI labels in the source mask. Use 'auto' to infer binary masks or use label 2 "
            "for the current landcover convention."
        ),
    )
    parser.add_argument(
        "--grid-rows",
        type=int,
        help="Target number of rows in the pygame grid. If omitted, inferred from block size.",
    )
    parser.add_argument(
        "--grid-cols",
        type=int,
        help="Target number of columns in the pygame grid. If omitted, inferred from block size.",
    )
    parser.add_argument(
        "--source-block-size",
        type=int,
        default=128,
        help="Source pixels grouped into one pygame cell when grid rows/cols are not provided.",
    )
    parser.add_argument(
        "--roi-threshold",
        type=float,
        default=0.50,
        help="Fraction of ROI pixels required for a cell to become value 1.",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=0,
        help="Display size of each pygame cell. Use 0 to auto-fit the window.",
    )
    parser.add_argument(
        "--blank-rows",
        type=int,
        default=24,
        help="Rows used when no mask is provided.",
    )
    parser.add_argument(
        "--blank-cols",
        type=int,
        default=32,
        help="Columns used when no mask is provided.",
    )
    parser.add_argument(
        "--window-max-width",
        type=int,
        default=1500,
        help="Soft maximum width used when auto-fitting the window.",
    )
    parser.add_argument(
        "--window-max-height",
        type=int,
        default=920,
        help="Soft maximum height used when auto-fitting the window.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("pygame_binary_outputs"),
        help="Directory used when saving the edited grid.",
    )
    parser.add_argument(
        "--save-prefix",
        help="Optional filename prefix for saved outputs.",
    )
    parser.add_argument(
        "--show-values",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Show or hide the numeric 0/1 value inside each cell.",
    )
    parser.add_argument(
        "--print-summary",
        action="store_true",
        help="Print grid statistics before opening pygame.",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Only prepare the grid and print stats without opening pygame.",
    )
    return parser.parse_args()


def require_pygame():
    try:
        import pygame
    except ImportError as exc:
        raise SystemExit(
            "Pygame is not installed in the active environment. "
            "Run this script with an environment that has pygame."
        ) from exc
    return pygame


def parse_label_spec(raw: str) -> list[int] | None:
    normalized = raw.strip().lower()
    if normalized in {"", "auto"}:
        return None
    if normalized in {"none", "null"}:
        return []
    return [int(value.strip()) for value in raw.split(",") if value.strip()]


def load_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.array(image.convert("L"), dtype=np.uint8)


def remap_to_binary(mask: np.ndarray, roi_labels: list[int] | None) -> np.ndarray:
    unique_values = sorted(int(value) for value in np.unique(mask))
    unique_set = set(unique_values)

    if roi_labels is not None:
        if not roi_labels:
            return np.zeros_like(mask, dtype=np.uint8)
        return np.isin(mask, roi_labels).astype(np.uint8)

    if unique_set.issubset({0, 1}):
        return (mask > 0).astype(np.uint8)
    if unique_set.issubset({0, 255}):
        return (mask > 0).astype(np.uint8)
    if 2 in unique_set:
        return (mask == 2).astype(np.uint8)
    if len(unique_values) == 2 and 0 in unique_set:
        roi_value = max(unique_values)
        return (mask == roi_value).astype(np.uint8)

    raise ValueError(
        "Could not infer ROI labels from the source mask. "
        "Pass --roi-labels explicitly, for example --roi-labels 2 or --roi-labels 1."
    )


def resolve_grid_shape(
    mask_shape: tuple[int, int],
    grid_rows: int | None,
    grid_cols: int | None,
    source_block_size: int,
) -> tuple[int, int]:
    height, width = mask_shape

    if grid_rows is not None and grid_rows <= 0:
        raise ValueError("--grid-rows must be positive.")
    if grid_cols is not None and grid_cols <= 0:
        raise ValueError("--grid-cols must be positive.")
    if source_block_size <= 0:
        raise ValueError("--source-block-size must be positive.")

    if grid_rows is None and grid_cols is None:
        rows = max(1, math.ceil(height / source_block_size))
        cols = max(1, math.ceil(width / source_block_size))
        return rows, cols

    if grid_rows is None:
        assert grid_cols is not None
        grid_rows = max(1, round(height * grid_cols / max(width, 1)))
    if grid_cols is None:
        assert grid_rows is not None
        grid_cols = max(1, round(width * grid_rows / max(height, 1)))
    return int(grid_rows), int(grid_cols)


def mask_to_grid(
    binary_mask: np.ndarray,
    grid_rows: int | None,
    grid_cols: int | None,
    source_block_size: int,
    roi_threshold: float,
) -> np.ndarray:
    if not 0.0 <= roi_threshold <= 1.0:
        raise ValueError("--roi-threshold must be between 0 and 1.")

    rows, cols = resolve_grid_shape(binary_mask.shape, grid_rows, grid_cols, source_block_size)
    row_edges = np.linspace(0, binary_mask.shape[0], rows + 1, dtype=int)
    col_edges = np.linspace(0, binary_mask.shape[1], cols + 1, dtype=int)
    grid = np.zeros((rows, cols), dtype=np.uint8)

    for row in range(rows):
        y0 = int(row_edges[row])
        y1 = int(row_edges[row + 1])
        for col in range(cols):
            x0 = int(col_edges[col])
            x1 = int(col_edges[col + 1])
            block = binary_mask[y0:y1, x0:x1]
            if block.size == 0:
                continue
            grid[row, col] = 1 if float(block.mean()) >= roi_threshold else 0

    return grid


def create_blank_grid(rows: int, cols: int) -> np.ndarray:
    if rows <= 0 or cols <= 0:
        raise ValueError("Blank grid rows and cols must be positive.")
    return np.zeros((rows, cols), dtype=np.uint8)


def summarize_grid(grid: np.ndarray, source_path: Path | None) -> str:
    roi_cells = int(grid.sum())
    total_cells = int(grid.size)
    ratio = 100.0 * roi_cells / max(total_cells, 1)
    source_text = "blank grid" if source_path is None else str(source_path.resolve())
    return (
        f"Source: {source_text}\n"
        f"Grid shape: {grid.shape[0]} rows x {grid.shape[1]} cols\n"
        f"ROI cells (value 1): {roi_cells}/{total_cells} ({ratio:.2f}%)"
    )


def resolve_save_prefix(args: argparse.Namespace, source_path: Path | None) -> str:
    if args.save_prefix:
        return args.save_prefix
    if source_path is not None:
        return f"{source_path.stem}_binary_grid"
    return "binary_grid"


def save_grid(grid: np.ndarray, output_dir: Path, prefix: str, source_path: Path | None) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    image_path = output_dir / f"{prefix}.png"
    json_path = output_dir / f"{prefix}.json"

    Image.fromarray((grid * 255).astype(np.uint8), mode="L").save(image_path)
    payload = {
        "source_mask": None if source_path is None else str(source_path.resolve()),
        "semantics": {
            "0": "non_roi_or_not_of_interest",
            "1": "roi_or_area_of_interest",
        },
        "rows": int(grid.shape[0]),
        "cols": int(grid.shape[1]),
        "roi_cells": int(grid.sum()),
        "total_cells": int(grid.size),
        "grid": grid.astype(int).tolist(),
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return image_path, json_path


def resolve_display_cell_size(
    rows: int,
    cols: int,
    requested_size: int,
    window_max_width: int,
    window_max_height: int,
    hud_height: int,
) -> int:
    if requested_size > 0:
        return requested_size

    available_width = max(window_max_width - 24, 120)
    available_height = max(window_max_height - hud_height - 24, 120)
    by_width = max(8, available_width // max(cols, 1))
    by_height = max(8, available_height // max(rows, 1))
    return max(10, min(28, by_width, by_height))


def run_pygame_editor(
    grid: np.ndarray,
    original_grid: np.ndarray,
    source_path: Path | None,
    args: argparse.Namespace,
) -> None:
    pygame = require_pygame()
    pygame.init()
    pygame.font.init()

    hud_height = 112
    rows, cols = grid.shape
    cell_size = resolve_display_cell_size(
        rows=rows,
        cols=cols,
        requested_size=int(args.cell_size),
        window_max_width=int(args.window_max_width),
        window_max_height=int(args.window_max_height),
        hud_height=hud_height,
    )
    width = cols * cell_size
    height = rows * cell_size + hud_height

    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("Binary ROI Grid - 0 non-ROI, 1 ROI")
    font = pygame.font.SysFont("consolas", max(12, min(20, int(cell_size * 0.62))), bold=True)
    small_font = pygame.font.SysFont("consolas", 15)
    clock = pygame.time.Clock()

    colors = {
        0: (78, 84, 92),
        1: (52, 199, 89),
    }
    text_colors = {
        0: (242, 242, 242),
        1: (10, 44, 16),
    }
    hud_bg = (247, 248, 250)
    hud_border = (203, 208, 214)
    grid_line = (140, 146, 152)

    show_values = bool(args.show_values)
    left_down = False
    right_down = False
    running = True
    prefix = resolve_save_prefix(args, source_path)

    def set_cell(row: int, col: int, value: int) -> None:
        if 0 <= row < rows and 0 <= col < cols:
            grid[row, col] = value

    def save_current_grid() -> None:
        image_path, json_path = save_grid(
            grid=grid,
            output_dir=args.output_dir,
            prefix=prefix,
            source_path=source_path,
        )
        print(f"Saved PNG:  {image_path.resolve()}")
        print(f"Saved JSON: {json_path.resolve()}")

    try:
        while running:
            dt = clock.tick(60)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key == pygame.K_g:
                        show_values = not show_values
                    elif event.key == pygame.K_c:
                        grid.fill(0)
                    elif event.key == pygame.K_r:
                        grid[:, :] = original_grid
                    elif event.key == pygame.K_s:
                        save_current_grid()
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
            if mouse_y >= hud_height:
                col = mouse_x // cell_size
                row = (mouse_y - hud_height) // cell_size
                if 0 <= row < rows and 0 <= col < cols:
                    if left_down:
                        set_cell(row, col, 1)
                    elif right_down:
                        set_cell(row, col, 0)

            screen.fill((233, 236, 239))
            pygame.draw.rect(screen, hud_bg, (0, 0, width, hud_height))
            pygame.draw.line(screen, hud_border, (0, hud_height - 1), (width, hud_height - 1), 2)

            roi_cells = int(grid.sum())
            total_cells = int(grid.size)
            hovered = None
            if mouse_y >= hud_height:
                col = mouse_x // cell_size
                row = (mouse_y - hud_height) // cell_size
                if 0 <= row < rows and 0 <= col < cols:
                    hovered = (row, col, int(grid[row, col]))

            lines = [
                "Binary ROI grid viewer/editor",
                "0 = non-ROI / vung khong quan tam | 1 = ROI / vung quan tam",
                f"ROI cells: {roi_cells}/{total_cells} | Cell size: {cell_size}px | Values: {'ON' if show_values else 'OFF'}",
                "Left click paint 1 | Right click paint 0 | G toggle values | R reset | C clear | S save | ESC quit",
            ]
            if hovered is not None:
                lines.append(f"Cursor: row={hovered[0]}, col={hovered[1]}, value={hovered[2]}")
            elif source_path is not None:
                lines.append(f"Source mask: {source_path.name}")
            else:
                lines.append("Source mask: blank grid")

            for index, line in enumerate(lines):
                text_surface = small_font.render(line, True, (32, 37, 41))
                screen.blit(text_surface, (14, 12 + index * 18))

            for row in range(rows):
                for col in range(cols):
                    x = col * cell_size
                    y = hud_height + row * cell_size
                    rect = pygame.Rect(x, y, cell_size, cell_size)
                    value = int(grid[row, col])
                    pygame.draw.rect(screen, colors[value], rect)
                    pygame.draw.rect(screen, grid_line, rect, width=1)

                    if show_values:
                        label = font.render(str(value), True, text_colors[value])
                        label_rect = label.get_rect(center=rect.center)
                        screen.blit(label, label_rect)

            fps_surface = small_font.render(f"FPS: {clock.get_fps():4.1f}", True, (32, 37, 41))
            screen.blit(fps_surface, (width - 110, 12))
            dt_surface = small_font.render(f"dt: {dt:3d} ms", True, (32, 37, 41))
            screen.blit(dt_surface, (width - 110, 30))
            pygame.display.flip()
    finally:
        pygame.quit()


def prepare_grid(args: argparse.Namespace) -> tuple[np.ndarray, Path | None]:
    if args.mask_path is None:
        grid = create_blank_grid(rows=int(args.blank_rows), cols=int(args.blank_cols))
        return grid, None

    mask = load_mask(args.mask_path)
    roi_labels = parse_label_spec(args.roi_labels)
    binary_mask = remap_to_binary(mask, roi_labels)
    grid = mask_to_grid(
        binary_mask=binary_mask,
        grid_rows=args.grid_rows,
        grid_cols=args.grid_cols,
        source_block_size=int(args.source_block_size),
        roi_threshold=float(args.roi_threshold),
    )
    return grid, args.mask_path


def main() -> None:
    args = parse_args()
    grid, source_path = prepare_grid(args)

    if args.print_summary or args.no_gui:
        print(summarize_grid(grid, source_path))

    if args.no_gui:
        return

    original_grid = grid.copy()
    run_pygame_editor(grid=grid, original_grid=original_grid, source_path=source_path, args=args)


if __name__ == "__main__":
    main()
