import math
import os
import random
from dataclasses import dataclass

import pygame

from config.settings import (
    LAYER_COFRE_CLOSED,
    LAYER_COFRE_OPEN,
    SPRITES_DIR,
    TILE_SIZE,
)


FRAGMENT_FILES = ("k-frag1.png", "k-frag2.png", "k-frag3.png")
POTION_FILES = {
    "vida": "pos-vida.png",
    "escudo": "pos-escudo.png",
    "poder": "pos-poder.png",
}
KEY_FILE = "llave.png"
SALAMI_FILE = "salami.png"

# Coordenadas de tiles indicadas por el usuario para el item del cofre
CHEST_REWARD_START_TILE = (15, 9)
CHEST_REWARD_END_TILE = (15, 8)
SPAWN_AREA_LAYER_CANDIDATES = ("inside-terrain", "inside the ring")


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

        self.fragment_images = [self._load_icon(name) for name in FRAGMENT_FILES]
        self.key_image = self._load_icon(KEY_FILE)
        self.salami_image = self._load_icon(SALAMI_FILE)
        self.potion_images = {
            potion_type: self._load_icon(sprite_name)
            for potion_type, sprite_name in POTION_FILES.items()
        }

        self.spawn_polygons = self._load_spawn_polygons()
        if not self.spawn_polygons:
            print("[items] Warning: no se encontro capa de spawn poligonal (inside-terrain). Se usara todo el mapa caminable.")

        self.walkable_points = self._build_walkable_points()

        self.fragments_collected = 0
        self.active_fragment: Pickup | None = None
        self.next_fragment_spawn_ms = pygame.time.get_ticks() + 600

        self.key_anim: dict | None = None

        self.chest_opened = False
        self.chest_trigger_rect = self._build_chest_trigger_rect()

        self.salami_launch: dict | None = None
        self.salami_pickup: Pickup | None = None

        now = pygame.time.get_ticks()
        self.active_potions: dict[str, Pickup] = {}
        self.next_potion_spawn_ms = {
            "vida": now + self.rng.randint(1800, 3200),
            "escudo": now + self.rng.randint(2300, 4200),
            "poder": now + self.rng.randint(3000, 5200),
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

        for layer in getattr(self.game_map.tmx_data, "objectgroups", []):
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
        if not hasattr(player, "key_fragments"):
            player.key_fragments = 0
        if not hasattr(player, "has_key"):
            player.has_key = False
        if not hasattr(player, "has_salami"):
            player.has_salami = False

    def _collect_existing_positions(self) -> list[pygame.Vector2]:
        positions: list[pygame.Vector2] = []
        if self.active_fragment is not None:
            positions.append(self.active_fragment.pos)
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

    def _spawn_next_fragment(self, now_ms: int, player):
        if self.fragments_collected >= len(self.fragment_images):
            return
        spawn_pos = self._pick_spawn_point(player, min_player_distance=TILE_SIZE * 3.0)
        if spawn_pos is None:
            self.next_fragment_spawn_ms = now_ms + 500
            return

        idx = self.fragments_collected
        self.active_fragment = Pickup(
            kind="fragment",
            subtype=str(idx + 1),
            image=self.fragment_images[idx],
            pos=spawn_pos,
            spawned_ms=now_ms,
            lifetime_ms=None,
            phase=self.rng.random() * math.tau,
            state="spawning",
            state_ms=now_ms,
        )

    def _start_key_animation(self, now_ms: int, player):
        self.key_anim = {
            "start_ms": now_ms,
            "duration_ms": 1100,
            "origin": pygame.Vector2(float(player.rect.centerx), float(player.rect.top + 8)),
        }

    def _update_fragments(self, now_ms: int, player, allow_pickups: bool):
        if (
            self.fragments_collected < 3
            and self.active_fragment is None
            and self.key_anim is None
            and now_ms >= self.next_fragment_spawn_ms
        ):
            self._spawn_next_fragment(now_ms, player)

        if self.active_fragment is None:
            return

        if allow_pickups and self.active_fragment.state in ("spawning", "idle"):
            if self.active_fragment.collision_rect(now_ms).colliderect(player.hitbox):
                self.active_fragment.start_collect(now_ms)

        result = self.active_fragment.update(now_ms)
        if result == "collected":
            self.fragments_collected += 1
            player.key_fragments = self.fragments_collected
            self.active_fragment = None
            if self.fragments_collected >= 3:
                self._start_key_animation(now_ms, player)
            else:
                self.next_fragment_spawn_ms = now_ms + 900

    def _update_key_animation(self, now_ms: int, player):
        if self.key_anim is None:
            return
        duration = self.key_anim["duration_ms"]
        if now_ms - self.key_anim["start_ms"] >= duration:
            player.has_key = True
            self.key_anim = None

    def _player_near_chest(self, player) -> bool:
        if self.chest_trigger_rect is None:
            return False
        return player.hitbox.colliderect(self.chest_trigger_rect)

    def _tile_center(self, tile_x: int, tile_y: int) -> pygame.Vector2:
        return pygame.Vector2(
            float((tile_x * self.game_map.tile_w) + (self.game_map.tile_w // 2)),
            float((tile_y * self.game_map.tile_h) + (self.game_map.tile_h // 2)),
        )

    def _open_chest(self, now_ms: int):
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
        if collected:
            self.next_potion_spawn_ms[potion_type] = now_ms + self.rng.randint(2400, 5200)
        else:
            self.next_potion_spawn_ms[potion_type] = now_ms + self.rng.randint(1800, 4200)

    def _apply_potion(self, potion_type: str, player):
        if potion_type == "vida":
            player.heal(24)
        elif potion_type == "escudo":
            player.shield = min(player.max_shield, player.shield + 22)
        elif potion_type == "poder":
            player.energy = min(player.max_energy, player.energy + 30)

    def _spawn_potions(self, now_ms: int, player):
        for potion_type in POTION_FILES:
            if potion_type in self.active_potions:
                continue
            if now_ms < self.next_potion_spawn_ms[potion_type]:
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
                lifetime_ms=7000,
                phase=self.rng.random() * math.tau,
                state="spawning",
                state_ms=now_ms,
            )

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
        self._update_fragments(now_ms, player, allow_pickups)
        self._update_key_animation(now_ms, player)

        if player.has_key and not self.chest_opened and self._player_near_chest(player):
            self._open_chest(now_ms)

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

        if self.active_fragment is not None:
            x, y, alpha, scale = self.active_fragment.draw_params(now_ms)
            draw_entries.append((y, self.active_fragment.image, x, y, alpha, scale))

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
        if self.key_anim is None:
            return

        now_ms = pygame.time.get_ticks()
        elapsed = now_ms - self.key_anim["start_ms"]
        duration = self.key_anim["duration_ms"]
        t = max(0.0, min(1.0, elapsed / max(duration, 1)))

        # El origen sigue al jugador para que la obtencion se sienta "anclada"
        origin_x = float(player.rect.centerx)
        origin_y = float(player.rect.top + 8)

        if t <= 0.75:
            rise_t = t / 0.75
            y = origin_y - (14.0 + 28.0 * rise_t)
            alpha = 255
            scale = 0.72 + (0.36 * rise_t)
        else:
            fade_t = (t - 0.75) / 0.25
            y = origin_y - 42.0 + (10.0 * fade_t)
            alpha = int(255 * (1.0 - fade_t))
            scale = 1.08 - (0.22 * fade_t)

        self._draw_sprite(
            target_surface=target_surface,
            camera=camera,
            image=self.key_image,
            x=origin_x,
            y=y,
            alpha=alpha,
            scale=scale,
        )
