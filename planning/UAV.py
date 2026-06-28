from __future__ import annotations

import numpy as np


class UAV:
    def __init__(
        self,
        path,
        speed: float = 180.0,
        arrival_tolerance: float = 1.0,
        trail_spacing: float = 2.0,
        max_trail_points: int = 5000,
    ) -> None:
        self.path = np.asarray(path, dtype=float)
        if self.path.ndim != 2 or self.path.shape[1] != 2 or len(self.path) == 0:
            raise ValueError("path must be an array of shape (n, 2).")

        self.speed = float(speed)
        self.arrival_tolerance = float(arrival_tolerance)
        self.trail_spacing = float(trail_spacing)
        self.max_trail_points = int(max_trail_points)
        self._segment_lengths = (
            np.linalg.norm(self.path[1:] - self.path[:-1], axis=1)
            if len(self.path) > 1
            else np.empty(0, dtype=float)
        )
        self.total_distance = float(self._segment_lengths.sum())
        self.reset()

    def reset(self) -> None:
        self.position = self.path[0].copy()
        if len(self.path) > 1:
            direction = self.path[1] - self.path[0]
            norm = float(np.linalg.norm(direction))
            self.heading = direction / norm if norm > 1e-6 else np.array([1.0, 0.0], dtype=float)
            self._target_index = 1
            self.finished = False
        else:
            self.heading = np.array([1.0, 0.0], dtype=float)
            self._target_index = 0
            self.finished = True
        self.travelled_distance = 0.0
        self.trail = [self.position.copy()]

    @property
    def current_target_index(self) -> int:
        return min(self._target_index, len(self.path) - 1)

    @property
    def progress_ratio(self) -> float:
        if self.total_distance <= 1e-6:
            return 1.0
        return min(self.travelled_distance / self.total_distance, 1.0)

    def set_speed(self, speed: float) -> None:
        self.speed = max(0.0, float(speed))

    def _append_trail(self, force: bool = False) -> None:
        if force or np.linalg.norm(self.position - self.trail[-1]) >= self.trail_spacing:
            self.trail.append(self.position.copy())
            overflow = len(self.trail) - self.max_trail_points
            if overflow > 0:
                del self.trail[:overflow]

    def update(self, dt: float) -> None:
        if self.finished or self.speed <= 0.0 or dt <= 0.0:
            return

        remaining_time = float(dt)
        while remaining_time > 0.0 and not self.finished:
            target = self.path[self._target_index]
            delta = target - self.position
            distance = float(np.linalg.norm(delta))

            if distance <= self.arrival_tolerance:
                self.position = target.copy()
                self._target_index += 1
                if self._target_index >= len(self.path):
                    self.finished = True
                    self._target_index = len(self.path) - 1
                    self._append_trail(force=True)
                    break
                continue

            direction = delta / distance
            step = self.speed * remaining_time
            self.heading = direction

            if step >= distance:
                self.position = target.copy()
                self.travelled_distance += distance
                remaining_time -= distance / max(self.speed, 1e-6)
                self._append_trail(force=True)
                self._target_index += 1
                if self._target_index >= len(self.path):
                    self.finished = True
                    self._target_index = len(self.path) - 1
                continue

            self.position = self.position + direction * step
            self.travelled_distance += step
            self._append_trail(force=False)
            remaining_time = 0.0
