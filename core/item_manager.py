import math
import os
import random
from dataclasses import dataclass

import pygame

from config.settings import (
    ENABLED_POTION_TYPES,
    LAYER_COFRE_CLOSED,
    LAYER_COFRE_OPEN,
    MAX_POTION_SPAWNS_PER_TYPE,
    SPRITES_DIR,
    TILE_SIZE,
)


ALL_POTION_FILES = {
    "vida": "pos-vida.png",
    "escudo": "pos-escudo.png",
    "poder": "pos-poder.png",
}
SALAMI_FILE = "salami.png"

# Coordenadas de tiles indicadas por el usuario para el item del cofre
CHEST_REWARD_START_TILE = (15, 9)
CHEST_REWARD_END_TILE = (15, 8)
SPAWN_AREA_LAYER_CANDIDATES = (
    "inside-terrain",
    "inside the ring",
    "inside t-brain",
    "inside_t_brain",
)


@dataclass
class Pickup:
    kind: str
    subtype: str
    image: pygame.Surface
    pos: pygame.Vector2
    spawned_ms: int
    lifetime_ms: int | None = None
    phase: float = 0.0
    state: str = "spawning"
    state_ms: int = 0

    SPAWN_MS = 320
    COLLECT_MS = 320
    FADE_MS = 500

    def start_collect(self, now_ms: int):
        if self.state in ("collecting", "fading"):
            return
        self.state = "collecting"
        self.state_ms = now_ms

    def update(self, now_ms: int) -> str | None:
        if self.state == "spawning":
            if now_ms - self.state_ms >= self.SPAWN_MS:
                self.state = "idle"
                self.state_ms = now_ms
        elif self.state == "idle":
            if self.lifetime_ms is not None and now_ms - self.spawned_ms >= self.lifetime_ms:
                self.state = "fading"
                self.state_ms = now_ms
        elif self.state == "fading":
            if now_ms - self.state_ms >= self.FADE_MS:
                return "expired"
        elif self.state == "collecting":
            if now_ms - self.state_ms >= self.COLLECT_MS:
                return "collected"
        return None

    @staticmethod
    def _clamp01(value: float) -> float:
        return max(0.0, min(1.0, value))

    def draw_params(self, now_ms: int) -> tuple[float, float, int, float]:
        bob = math.sin((now_ms / 180.0) + self.phase) * 2.5
        x = float(self.pos.x)
        y = float(self.pos.y + bob)
        alpha = 255
        scale = 1.0

        if self.state == "spawning":
            t = self._clamp01((now_ms - self.state_ms) / self.SPAWN_MS)
            alpha = int(255 * t)
            scale = 0.55 + (0.45 * t)
            y += (1.0 - t) * 6.0
        elif self.state == "fading":
            t = self._clamp01((now_ms - self.state_ms) / self.FADE_MS)
            alpha = int(255 * (1.0 - t))
            scale = 1.0 + (0.1 * t)
        elif self.state == "collecting":
            t = self._clamp01((now_ms - self.state_ms) / self.COLLECT_MS)
            alpha = int(255 * (1.0 - t))
            scale = 1.0 + (0.35 * t)
            y -= 14.0 * t

        return x, y, alpha, scale

    def collision_rect(self, now_ms: int) -> pygame.Rect:
        x, y, _, _ = self.draw_params(now_ms)
        radius = max(8, int(min(self.image.get_width(), self.image.get_height()) * 0.30))
        return pygame.Rect(int(x - radius), int(y - radius), radius * 2, radius * 2)


class ItemManager:
    def __init__(self, game_map):
        self.game_map = game_map
        self.rng = random.Random()

        self.enabled_potion_types = tuple(
            potion_type for potion_type in ENABLED_POTION_TYPES
            if potion_type in ALL_POTION_FILES
        )
        if not self.enabled_potion_types:
            self.enabled_potion_types = ("vida",)

        self.salami_image = self._load_icon(SALAMI_FILE)
        self.potion_images = {
            potion_type: self._load_icon(ALL_POTION_FILES[potion_type])
            for potion_type in self.enabled_potion_types
        }

        self.spawn_polygons = self._load_spawn_polygons()
        if not self.spawn_polygons:
            print("[items] Warning: sin capa poligonal de spawn. Se usaran puntos caminables del mapa.")

        self.walkable_points = self._build_walkable_points()

        self.chest_opened = False
        self.chest_trigger_rect = self._build_chest_trigger_rect()

        self.salami_launch: dict | None = None
        self.salami_pickup: Pickup | None = None

        now = pygame.time.get_ticks()
        self.active_potions: dict[str, Pickup] = {}
        self.potion_spawn_count = {potion_type: 0 for potion_type in self.enabled_potion_types}
        self.next_potion_spawn_ms = {
            potion_type: now + self._next_potion_delay_ms(potion_type, collected=False, initial=True)
            for potion_type in self.enabled_potion_types
        }

    def _load_icon(self, filename: str) -> pygame.Surface:
        path = os.path.join(SPRITES_DIR, filename)
        target = int(TILE_SIZE * 0.90)
        try:
            image = pygame.image.load(path).convert_alpha()
            w, h = image.get_size()
            max_side = max(w, h, 1)
            factor = target / max_side
            new_size = (max(1, int(w * factor)), max(1, int(h * factor)))
            return pygame.transform.smoothscale(image, new_size)
        except Exception:
            fallback = pygame.Surface((target, target), pygame.SRCALPHA)
            pygame.draw.rect(fallback, (255, 0, 255), fallback.get_rect(), border_radius=4)
            return fallback

    @staticmethod
    def _normalize_layer_name(name: str) -> str:
        return str(name or "").strip().lower()

    @staticmethod
    def _extract_xy(point) -> tuple[float, float]:
        if hasattr(point, "x") and hasattr(point, "y"):
            return float(point.x), float(point.y)
        if isinstance(point, (tuple, list)) and len(point) >= 2:
            return float(point[0]), float(point[1])
        return 0.0, 0.0

    def _score_points_in_map(self, points: list[tuple[float, float]]) -> int:
        max_x = float(self.game_map.map_width)
        max_y = float(self.game_map.map_height)
        return sum(1 for x, y in points if 0.0 <= x <= max_x and 0.0 <= y <= max_y)

    def _normalize_object_polygon(self, obj, points) -> list[tuple[float, float]]:
        raw_points = [self._extract_xy(p) for p in points]
        ox = float(getattr(obj, "x", 0.0) or 0.0)
        oy = float(getattr(obj, "y", 0.0) or 0.0)
        offset_points = [(x + ox, y + oy) for x, y in raw_points]

        # Compatibilidad: algunos loaders traen puntos absolutos y otros relativos.
        if self._score_points_in_map(offset_points) > self._score_points_in_map(raw_points):
            return offset_points
        return raw_points

    def _load_spawn_polygons(self) -> list[list[tuple[float, float]]]:
        target_names = {self._normalize_layer_name(n) for n in SPAWN_AREA_LAYER_CANDIDATES}
        polygons: list[list[tuple[float, float]]] = []
        tmx_data = getattr(self.game_map, "tmx_data", None)

        # Sandbox/procedural maps: fallback to play area rect if available.
        play_area = getattr(self.game_map, "play_area_rect", None)
        if play_area is not None:
            polygons.append(
                [
                    (float(play_area.left), float(play_area.top)),
                    (float(play_area.right), float(play_area.top)),
                    (float(play_area.right), float(play_area.bottom)),
                    (float(play_area.left), float(play_area.bottom)),
                ]
            )
            return polygons

        if tmx_data is None:
            return polygons

        for layer in getattr(tmx_data, "objectgroups", []):
            layer_name = self._normalize_layer_name(getattr(layer, "name", ""))
            if layer_name not in target_names:
                continue

            for obj in layer:
                points = getattr(obj, "points", None)
                if points and len(points) >= 3:
                    polygon = self._normalize_object_polygon(obj, points)
                    if len(polygon) >= 3:
                        polygons.append(polygon)
                    continue

                ox = float(getattr(obj, "x", 0.0) or 0.0)
                oy = float(getattr(obj, "y", 0.0) or 0.0)
                ow = float(getattr(obj, "width", 0.0) or 0.0)
                oh = float(getattr(obj, "height", 0.0) or 0.0)
                if ow > 0 and oh > 0:
                    polygons.append(
                        [
                            (ox, oy),
                            (ox + ow, oy),
                            (ox + ow, oy + oh),
                            (ox, oy + oh),
                        ]
                    )

        return polygons

    @staticmethod
    def _point_on_segment(
        px: float, py: float,
        ax: float, ay: float,
        bx: float, by: float,
        eps: float = 1e-5,
    ) -> bool:
        cross = (px - ax) * (by - ay) - (py - ay) * (bx - ax)
        if abs(cross) > eps:
            return False

        dot = (px - ax) * (px - bx) + (py - ay) * (py - by)
        return dot <= eps

    def _point_in_polygon(self, x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
        inside = False
        n = len(polygon)
        if n < 3:
            return False

        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]

            if self._point_on_segment(x, y, xi, yi, xj, yj):
                return True

            y_diff = yj - yi
            if (yi > y) != (yj > y):
                x_cross = ((xj - xi) * (y - yi) / (y_diff if y_diff != 0 else 1e-9)) + xi
                if x < x_cross:
                    inside = not inside
            j = i

        return inside

    def _is_inside_spawn_zone(self, x: float, y: float) -> bool:
        if not self.spawn_polygons:
            return True
        return any(self._point_in_polygon(x, y, polygon) for polygon in self.spawn_polygons)

    def _is_rect_inside_spawn_zone(self, rect: pygame.Rect) -> bool:
        if not self.spawn_polygons:
            return True

        probes = (
            (rect.centerx, rect.centery),
            (rect.left, rect.top),
            (rect.right - 1, rect.top),
            (rect.left, rect.bottom - 1),
            (rect.right - 1, rect.bottom - 1),
        )
        return all(self._is_inside_spawn_zone(float(px), float(py)) for px, py in probes)

    def _build_walkable_points(self) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        tile_w, tile_h = self.game_map.tile_w, self.game_map.tile_h
        tiles_x = self.game_map.map_width // tile_w
        tiles_y = self.game_map.map_height // tile_h

        static_mask = getattr(self.game_map, "collision_mask", None)
        static_blocked_rects: list[pygame.Rect] = list(self.game_map.collision_rects)
        dynamic_blocked_rects: list[pygame.Rect] = list(self.game_map.get_dynamic_collisions())

        sample_size = int(TILE_SIZE * 0.62)
        sample_size = max(8, sample_size)
        half = sample_size // 2
        sample_mask = pygame.mask.Mask((sample_size, sample_size), fill=True)
        margin = 1

        for ty in range(margin, max(margin + 1, tiles_y - margin)):
            for tx in range(margin, max(margin + 1, tiles_x - margin)):
                cx = tx * tile_w + (tile_w // 2)
                cy = ty * tile_h + (tile_h // 2)
                sample = pygame.Rect(cx - half, cy - half, sample_size, sample_size)

                if not self._is_rect_inside_spawn_zone(sample):
                    continue

                if any(sample.colliderect(rect) for rect in dynamic_blocked_rects):
                    continue

                if static_mask is not None:
                    if static_mask.overlap(sample_mask, (sample.x, sample.y)):
                        continue
                elif any(sample.colliderect(rect) for rect in static_blocked_rects):
                    continue

                points.append((cx, cy))

        return points

    def _build_chest_trigger_rect(self) -> pygame.Rect | None:
        rects = self.game_map.dynamic_layer_rects.get(LAYER_COFRE_CLOSED, [])
        if not rects:
            return None
        merged = rects[0].copy()
        for rect in rects[1:]:
            merged.union_ip(rect)
        return merged.inflate(18, 18)

    def _ensure_player_fields(self, player):
        if not hasattr(player, "has_salami"):
            player.has_salami = False

    def _collect_existing_positions(self) -> list[pygame.Vector2]:
        positions: list[pygame.Vector2] = []
        positions.extend(pickup.pos for pickup in self.active_potions.values())
        if self.salami_pickup is not None:
            positions.append(self.salami_pickup.pos)
        return positions

    def _pick_spawn_point(self, player, min_player_distance: float = TILE_SIZE * 2.5) -> pygame.Vector2 | None:
        if not self.walkable_points:
            return None

        player_center = pygame.Vector2(player.hitbox.centerx, player.hitbox.centery)
        occupied = self._collect_existing_positions()

        for _ in range(60):
            px, py = self.rng.choice(self.walkable_points)
            point = pygame.Vector2(float(px), float(py))

            if point.distance_to(player_center) < min_player_distance:
                continue
            if any(point.distance_to(other) < TILE_SIZE * 1.5 for other in occupied):
                continue
            return point

        px, py = self.rng.choice(self.walkable_points)
        return pygame.Vector2(float(px), float(py))

    def get_enemy_spawn_points(
        self,
        count: int,
        player,
        min_player_distance: float = TILE_SIZE * 3.5,
        min_between_distance: float = TILE_SIZE * 2.4,
    ) -> list[pygame.Vector2]:
        points: list[pygame.Vector2] = []
        if count <= 0 or not self.walkable_points:
            return points

        max_attempts = max(80, count * 140)
        attempts = 0
        while len(points) < count and attempts < max_attempts:
            attempts += 1
            point = self._pick_spawn_point(player, min_player_distance=min_player_distance)
            if point is None:
                continue
            if any(point.distance_to(other) < min_between_distance for other in points):
                continue
            points.append(point)
        return points

    def _tile_center(self, tile_x: int, tile_y: int) -> pygame.Vector2:
        return pygame.Vector2(
            float((tile_x * self.game_map.tile_w) + (self.game_map.tile_w // 2)),
            float((tile_y * self.game_map.tile_h) + (self.game_map.tile_h // 2)),
        )

    def open_chest(self, now_ms: int | None = None):
        if self.chest_opened:
            return
        if now_ms is None:
            now_ms = pygame.time.get_ticks()
        self.chest_opened = True
        if LAYER_COFRE_CLOSED in self.game_map.layer_visible:
            self.game_map.layer_visible[LAYER_COFRE_CLOSED] = False
        if LAYER_COFRE_OPEN in self.game_map.layer_visible:
            self.game_map.layer_visible[LAYER_COFRE_OPEN] = True

        start_pos = self._tile_center(*CHEST_REWARD_START_TILE)
        end_pos = self._tile_center(*CHEST_REWARD_END_TILE)
        self.salami_launch = {
            "start_ms": now_ms,
            "duration_ms": 800,
            "from": start_pos,
            "to": end_pos,
        }

    def _update_salami_reward(self, now_ms: int, player, allow_pickups: bool):
        if self.salami_launch is not None:
            elapsed = now_ms - self.salami_launch["start_ms"]
            if elapsed >= self.salami_launch["duration_ms"]:
                end_pos = self.salami_launch["to"]
                self.salami_pickup = Pickup(
                    kind="reward",
                    subtype="salami",
                    image=self.salami_image,
                    pos=pygame.Vector2(float(end_pos.x), float(end_pos.y)),
                    spawned_ms=now_ms,
                    lifetime_ms=None,
                    phase=self.rng.random() * math.tau,
                    state="spawning",
                    state_ms=now_ms,
                )
                self.salami_launch = None

        if self.salami_pickup is None:
            return

        if allow_pickups and self.salami_pickup.state in ("spawning", "idle"):
            if self.salami_pickup.collision_rect(now_ms).colliderect(player.hitbox):
                self.salami_pickup.start_collect(now_ms)

        result = self.salami_pickup.update(now_ms)
        if result == "collected":
            player.has_salami = True
            player.heal(12)
            self.salami_pickup = None

    def _schedule_next_potion(self, potion_type: str, now_ms: int, collected: bool):
        if self.potion_spawn_count.get(potion_type, 0) >= MAX_POTION_SPAWNS_PER_TYPE:
            self.next_potion_spawn_ms[potion_type] = None
            return
        self.next_potion_spawn_ms[potion_type] = now_ms + self._next_potion_delay_ms(
            potion_type,
            collected=collected,
            initial=False,
        )

    def _apply_potion(self, potion_type: str, player):
        if potion_type == "vida":
            player.heal(28)
        elif potion_type == "escudo":
            player.shield = min(player.max_shield, player.shield + 22)
        elif potion_type == "poder":
            player.energy = min(player.max_energy, player.energy + 44)

    @staticmethod
    def _potion_lifetime_ms(potion_type: str) -> int:
        if potion_type == "vida":
            return 22000
        if potion_type == "escudo":
            return 11800
        return 10400

    def _next_potion_delay_ms(self, potion_type: str, collected: bool, initial: bool = False) -> int:
        # Vida aparece con mayor frecuencia que escudo/poder para sostener combates largos.
        if potion_type == "vida":
            if initial:
                return self.rng.randint(520, 1120)
            if collected:
                return self.rng.randint(760, 1550)
            return self.rng.randint(620, 1280)
        if potion_type == "escudo":
            if initial:
                return self.rng.randint(1180, 2100)
            if collected:
                return self.rng.randint(1650, 2800)
            return self.rng.randint(1340, 2420)
        # poder
        if initial:
            return self.rng.randint(1380, 2360)
        if collected:
            return self.rng.randint(1900, 3050)
        return self.rng.randint(1550, 2700)

    def get_active_potion_positions(self, potion_types: tuple[str, ...] = ("vida",)) -> list[tuple[str, pygame.Vector2]]:
        targets: list[tuple[str, pygame.Vector2]] = []
        for potion_type, pickup in self.active_potions.items():
            if potion_type not in potion_types:
                continue
            if pickup.state not in ("spawning", "idle"):
                continue
            targets.append((potion_type, pygame.Vector2(float(pickup.pos.x), float(pickup.pos.y))))
        return targets

    def consume_potion_at(
        self,
        world_x: float,
        world_y: float,
        radius: float,
        potion_types: tuple[str, ...] = ("vida",),
    ) -> str | None:
        now_ms = pygame.time.get_ticks()
        center = pygame.Vector2(float(world_x), float(world_y))
        for potion_type, pickup in list(self.active_potions.items()):
            if potion_type not in potion_types:
                continue
            if pickup.state not in ("spawning", "idle"):
                continue
            if center.distance_to(pickup.pos) > float(radius):
                continue
            del self.active_potions[potion_type]
            self._schedule_next_potion(potion_type, now_ms, collected=True)
            return potion_type
        return None

    def _spawn_potions(self, now_ms: int, player):
        for potion_type in self.enabled_potion_types:
            if potion_type in self.active_potions:
                continue
            if self.potion_spawn_count.get(potion_type, 0) >= MAX_POTION_SPAWNS_PER_TYPE:
                continue
            next_spawn_at = self.next_potion_spawn_ms.get(potion_type)
            if next_spawn_at is None or now_ms < next_spawn_at:
                continue

            spawn_pos = self._pick_spawn_point(player, min_player_distance=TILE_SIZE * 2.2)
            if spawn_pos is None:
                self.next_potion_spawn_ms[potion_type] = now_ms + 700
                continue

            self.active_potions[potion_type] = Pickup(
                kind="potion",
                subtype=potion_type,
                image=self.potion_images[potion_type],
                pos=spawn_pos,
                spawned_ms=now_ms,
                lifetime_ms=self._potion_lifetime_ms(potion_type),
                phase=self.rng.random() * math.tau,
                state="spawning",
                state_ms=now_ms,
            )
            self.potion_spawn_count[potion_type] = self.potion_spawn_count.get(potion_type, 0) + 1

    def _update_potions(self, now_ms: int, player, allow_pickups: bool):
        self._spawn_potions(now_ms, player)

        for potion_type, pickup in list(self.active_potions.items()):
            if allow_pickups and pickup.state in ("spawning", "idle"):
                if pickup.collision_rect(now_ms).colliderect(player.hitbox):
                    pickup.start_collect(now_ms)

            result = pickup.update(now_ms)
            if result == "collected":
                self._apply_potion(potion_type, player)
                del self.active_potions[potion_type]
                self._schedule_next_potion(potion_type, now_ms, collected=True)
            elif result == "expired":
                del self.active_potions[potion_type]
                self._schedule_next_potion(potion_type, now_ms, collected=False)

    def update(self, player, intro_active: bool = False):
        now_ms = pygame.time.get_ticks()
        self._ensure_player_fields(player)

        allow_pickups = not intro_active
        self._update_salami_reward(now_ms, player, allow_pickups)
        self._update_potions(now_ms, player, allow_pickups)

    @staticmethod
    def _draw_sprite(
        target_surface: pygame.Surface,
        camera,
        image: pygame.Surface,
        x: float,
        y: float,
        alpha: int,
        scale: float,
    ):
        width = max(1, int(image.get_width() * scale))
        height = max(1, int(image.get_height() * scale))
        if width != image.get_width() or height != image.get_height():
            frame = pygame.transform.smoothscale(image, (width, height))
        else:
            frame = image

        if alpha < 255:
            frame = frame.copy()
            frame.set_alpha(max(0, min(255, alpha)))

        sx, sy = camera.apply_pos(int(x), int(y))
        target_surface.blit(frame, (sx - frame.get_width() // 2, sy - frame.get_height() // 2))

    def draw_world(self, target_surface: pygame.Surface, camera):
        now_ms = pygame.time.get_ticks()

        draw_entries: list[tuple[float, pygame.Surface, float, float, int, float]] = []

        for pickup in self.active_potions.values():
            x, y, alpha, scale = pickup.draw_params(now_ms)
            draw_entries.append((y, pickup.image, x, y, alpha, scale))

        if self.salami_pickup is not None:
            x, y, alpha, scale = self.salami_pickup.draw_params(now_ms)
            draw_entries.append((y, self.salami_pickup.image, x, y, alpha, scale))

        if self.salami_launch is not None:
            elapsed = now_ms - self.salami_launch["start_ms"]
            duration = self.salami_launch["duration_ms"]
            t = max(0.0, min(1.0, elapsed / max(duration, 1)))
            ease = 1.0 - ((1.0 - t) ** 2)
            pos = self.salami_launch["from"].lerp(self.salami_launch["to"], ease)
            arc = math.sin(t * math.pi) * 12.0
            x = float(pos.x)
            y = float(pos.y - arc)
            alpha = int(255 * t)
            scale = 0.68 + (0.32 * t)
            draw_entries.append((y, self.salami_image, x, y, alpha, scale))

        draw_entries.sort(key=lambda item: item[0])
        for _, image, x, y, alpha, scale in draw_entries:
            self._draw_sprite(target_surface, camera, image, x, y, alpha, scale)

    def draw_overlay(self, target_surface: pygame.Surface, camera, player):
        # Sin overlay temporal por ahora (antes se usaba para animacion de llave).
        return
