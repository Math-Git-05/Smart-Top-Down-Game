from __future__ import annotations

import random

import pygame

from config.settings import (
    LAYER_COFRE_CLOSED,
    LAYER_PUERTA_CLOSED,
    LAYER_PUERTA_OPEN,
    TILE_SIZE,
)


class SandboxMap:
    """Procedural sandbox arena with handcrafted collisions and an exit gate."""

    def __init__(self, width_tiles: int = 44, height_tiles: int = 32):
        self.tile_w = TILE_SIZE
        self.tile_h = TILE_SIZE
        self.tiles_x = width_tiles
        self.tiles_y = height_tiles
        self.map_width = width_tiles * self.tile_w
        self.map_height = height_tiles * self.tile_h

        self.layers_under_player = (
            "sandbox-floor",
            "sandbox-walls",
            LAYER_PUERTA_OPEN,
            LAYER_PUERTA_CLOSED,
        )
        self.layers_over_player = ()

        self.exit_rect = pygame.Rect(
            (self.map_width // 2) - (self.tile_w * 2),
            self.tile_h,
            self.tile_w * 4,
            self.tile_h,
        )
        self.play_area_rect = pygame.Rect(
            self.tile_w * 2,
            self.tile_h * 2,
            self.map_width - (self.tile_w * 4),
            self.map_height - (self.tile_h * 4),
        )
        self._gate_rect = pygame.Rect(
            self.exit_rect.x,
            self.exit_rect.y + self.tile_h,
            self.exit_rect.width,
            self.tile_h,
        )

        self.dynamic_layer_rects = {
            LAYER_PUERTA_CLOSED: [self._gate_rect.copy()],
            LAYER_COFRE_CLOSED: [],
        }

        self.layer_visible: dict[str, bool] = {
            "sandbox-floor": True,
            "sandbox-walls": True,
            LAYER_PUERTA_OPEN: False,
            LAYER_PUERTA_CLOSED: True,
        }

        self.collision_rects = self._build_static_collision_rects()
        self.collision_mask = self._build_collision_mask(self.collision_rects)
        self.hazard_rects: list[pygame.Rect] = []
        self.hazard_centers: list[tuple[int, int]] = []

        self._layer_surfaces = self._build_layer_surfaces()
        self._spawn_points = self._build_spawn_points()

    def _build_static_collision_rects(self) -> list[pygame.Rect]:
        t = self.tile_w
        w = self.map_width
        h = self.map_height

        rects = [
            pygame.Rect(0, 0, w, t),
            pygame.Rect(0, h - t, w, t),
            pygame.Rect(0, 0, t, h),
            pygame.Rect(w - t, 0, t, h),
        ]

        arena_blocks = [
            pygame.Rect((w // 2) - 5 * t, (h // 2) - 3 * t, 2 * t, 6 * t),
            pygame.Rect((w // 2) + 3 * t, (h // 2) - 3 * t, 2 * t, 6 * t),
            pygame.Rect((w // 2) - t, (h // 2) - 6 * t, 2 * t, 2 * t),
            pygame.Rect((w // 2) - t, (h // 2) + 4 * t, 2 * t, 2 * t),
            pygame.Rect((w // 2) - 10 * t, (h // 2) - t, 3 * t, 2 * t),
            pygame.Rect((w // 2) + 7 * t, (h // 2) - t, 3 * t, 2 * t),
        ]
        rects.extend(arena_blocks)
        return rects

    def _build_collision_mask(self, rects: list[pygame.Rect]) -> pygame.mask.Mask:
        surf = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)
        for rect in rects:
            pygame.draw.rect(surf, (255, 255, 255, 255), rect)
        return pygame.mask.from_surface(surf)

    def _build_layer_surfaces(self) -> dict[str, pygame.Surface]:
        floor = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)
        wall = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)
        gate_closed = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)
        gate_open = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)

        for y in range(self.tiles_y):
            for x in range(self.tiles_x):
                base = (20, 36, 42) if (x + y) % 2 == 0 else (24, 42, 50)
                accent = (12, 23, 27) if (x + y) % 4 == 0 else base
                tile_rect = pygame.Rect(x * self.tile_w, y * self.tile_h, self.tile_w, self.tile_h)
                pygame.draw.rect(floor, base, tile_rect)
                pygame.draw.rect(floor, accent, tile_rect, width=1)

        for rect in self.collision_rects:
            pygame.draw.rect(wall, (70, 88, 95), rect)
            pygame.draw.rect(wall, (32, 44, 48), rect, width=2)

        pygame.draw.rect(gate_closed, (160, 84, 52), self._gate_rect)
        pygame.draw.rect(gate_closed, (96, 50, 30), self._gate_rect, width=2)

        pygame.draw.rect(gate_open, (60, 140, 86), self.exit_rect, width=3)

        return {
            "sandbox-floor": floor,
            "sandbox-walls": wall,
            LAYER_PUERTA_CLOSED: gate_closed,
            LAYER_PUERTA_OPEN: gate_open,
        }

    def _build_spawn_points(self) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        t = self.tile_w

        for ty in range(2, self.tiles_y - 2):
            for tx in range(2, self.tiles_x - 2):
                cx = tx * t + (t // 2)
                cy = ty * t + (t // 2)
                if not self.is_inside_play_area(cx, cy, margin=12):
                    continue
                probe = pygame.Rect(cx - 10, cy - 10, 20, 20)
                if any(probe.colliderect(rect) for rect in self.collision_rects):
                    continue
                if probe.colliderect(self._gate_rect.inflate(20, 20)):
                    continue
                points.append((cx, cy))

        return points

    def get_enemy_spawn_points(
        self,
        count: int,
        player,
        min_player_distance: float = TILE_SIZE * 4.0,
        min_between_distance: float = TILE_SIZE * 2.4,
    ) -> list[pygame.Vector2]:
        if count <= 0:
            return []

        rng = random.Random()
        player_pos = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))

        selected: list[pygame.Vector2] = []
        attempts = 0
        max_attempts = max(100, count * 200)

        while len(selected) < count and attempts < max_attempts:
            attempts += 1
            px, py = rng.choice(self._spawn_points)
            point = pygame.Vector2(float(px), float(py))
            if not self.is_inside_play_area(point.x, point.y, margin=12):
                continue

            if point.distance_to(player_pos) < min_player_distance:
                continue
            if any(point.distance_to(other) < min_between_distance for other in selected):
                continue
            selected.append(point)

        return selected

    def is_inside_play_area(self, x: float, y: float, margin: int = 8) -> bool:
        probe_rect = self.play_area_rect.inflate(-margin * 2, -margin * 2)
        return probe_rect.collidepoint(float(x), float(y))

    def draw_layers(self, target_surface: pygame.Surface, layer_names, offset=(0, 0)):
        ox, oy = offset
        for layer_name in layer_names:
            if not self.layer_visible.get(layer_name, True):
                continue
            layer_surface = self._layer_surfaces.get(layer_name)
            if layer_surface is None:
                continue
            target_surface.blit(layer_surface, (-ox, -oy))

    def get_dynamic_collisions(self) -> list[pygame.Rect]:
        rects: list[pygame.Rect] = []
        for layer_name, layer_rects in self.dynamic_layer_rects.items():
            if self.layer_visible.get(layer_name, True):
                rects.extend(layer_rects)
        return rects

    def draw_debug_collisions(self, surface: pygame.Surface, offset=(0, 0)):
        ox, oy = offset
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        for rect in self.collision_rects:
            pygame.draw.rect(overlay, (255, 0, 0, 80), rect.move(-ox, -oy))
        for rect in self.get_dynamic_collisions():
            pygame.draw.rect(overlay, (0, 0, 255, 100), rect.move(-ox, -oy))
        pygame.draw.rect(overlay, (0, 255, 120, 120), self.exit_rect.move(-ox, -oy), width=2)
        surface.blit(overlay, (0, 0))

    def get_layers_at_world_point(self, world_x: float, world_y: float, include_hidden: bool = True) -> list[str]:
        x = int(world_x)
        y = int(world_y)
        if x < 0 or y < 0 or x >= self.map_width or y >= self.map_height:
            return []

        labels: list[str] = []
        for layer_name, layer_surface in self._layer_surfaces.items():
            visible = self.layer_visible.get(layer_name, True)
            if (not include_hidden) and (not visible):
                continue
            try:
                if layer_surface.get_at((x, y)).a > 0:
                    suffix = "" if visible else " [hidden]"
                    labels.append(f"tile:{layer_name}{suffix}")
            except Exception:
                continue

        if any(rect.collidepoint(x, y) for rect in self.collision_rects):
            labels.append("obj:Coli")
        for layer_name, rects in self.dynamic_layer_rects.items():
            if self.layer_visible.get(layer_name, True) and any(rect.collidepoint(x, y) for rect in rects):
                labels.append(f"dynamic:{layer_name}")

        return labels
