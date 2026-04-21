import math
import os
import random

import pygame

from config.settings import (
    ASSETS_DIR,
    ENEMY_A_DAMAGE,
    ENEMY_A_HEALTH,
    ENEMY_A_SPEED,
    ENEMY_A_VISION_RANGE,
    ENEMY_B_DAMAGE,
    ENEMY_B_HEALTH,
    ENEMY_B_SPEED,
    ENEMY_BULLET_SPEED,
    ENEMY_B_VISION_RANGE,
    ENEMY_C_DAMAGE,
    ENEMY_C_FLEE_RANGE,
    ENEMY_C_HEALTH,
    ENEMY_C_SPEED,
    ENEMY_C_VISION_RANGE,
    ENEMY_CLOSE_RANGE,
    ENEMY_LOW_HP_RATIO,
    ENEMY_MELEE_RANGE,
    TILE_SIZE,
)


MONSTER_BASE_DIR = os.path.join(
    ASSETS_DIR,
    "tilesets",
    "Ninja Adventure - Asset Pack",
    "Ninja Adventure - Asset Pack",
    "Actor",
    "Monster",
)

PIXEL_CRAWLER_MOBS_DIR = os.path.join(
    ASSETS_DIR,
    "tilesets",
    "Pixel Crawler - Free Pack",
    "Entities",
    "Mobs",
    "Skeleton Crew",
)

MONSTER_SPRITES_BY_TYPE = {
    "A": (
        os.path.join(MONSTER_BASE_DIR, "Slime4", "Slime4.png"),
        os.path.join(MONSTER_BASE_DIR, "Slime", "Slime.png"),
        os.path.join(PIXEL_CRAWLER_MOBS_DIR, "Skeleton - Warrior", "Run", "Run-Sheet.png"),
        os.path.join(MONSTER_BASE_DIR, "Grey Trex", "SpriteSheet.png"),
    ),
    "B": (
        os.path.join(MONSTER_BASE_DIR, "Dragon", "SpriteSheet.png"),
        os.path.join(MONSTER_BASE_DIR, "DragonYellow", "SpriteSheet.png"),
        os.path.join(PIXEL_CRAWLER_MOBS_DIR, "Skeleton - Mage", "Run", "Run-Sheet.png"),
        os.path.join(MONSTER_BASE_DIR, "Dragon", "SpriteSheet.png"),
    ),
    "C": (
        os.path.join(MONSTER_BASE_DIR, "Grey Trex", "SpriteSheet.png"),
        os.path.join(MONSTER_BASE_DIR, "TRex", "SpriteSheet.png"),
        os.path.join(PIXEL_CRAWLER_MOBS_DIR, "Skeleton - Rogue", "Run", "Run-Sheet.png"),
        os.path.join(ASSETS_DIR, "sprites", "gelatina_azul.png"),
    ),
}


def _resolve_sprite_path(sprite_entry: str | tuple[str, ...]) -> str:
    if isinstance(sprite_entry, tuple):
        for candidate in sprite_entry:
            if os.path.exists(candidate):
                return candidate
        return sprite_entry[0] if sprite_entry else ""
    return sprite_entry


def _safe_normalize(vec: pygame.Vector2) -> pygame.Vector2:
    if vec.length_squared() <= 1e-9:
        return pygame.Vector2(0.0, 0.0)
    return vec.normalize()


def _direction_from_vector(vec: pygame.Vector2) -> str:
    if abs(vec.x) >= abs(vec.y):
        return "right" if vec.x >= 0 else "left"
    return "down" if vec.y >= 0 else "up"


def _extract_frames(
    sheet: pygame.Surface,
    row: int,
    cols: int,
    frame_w: int,
    frame_h: int,
    fallback: pygame.Surface,
) -> list[pygame.Surface]:
    extracted: list[pygame.Surface] = []
    for col in range(cols):
        frame = sheet.subsurface((col * frame_w, row * frame_h, frame_w, frame_h)).copy()
        extracted.append(frame)
    return extracted or [fallback.copy()]


def _load_sheet_frames(sprite_path: str) -> dict[str, list[pygame.Surface]]:
    fallback_side = max(14, int(TILE_SIZE * 0.5))
    fallback = pygame.Surface((fallback_side, fallback_side), pygame.SRCALPHA)
    pygame.draw.circle(fallback, (220, 60, 60), (fallback_side // 2, fallback_side // 2), fallback_side // 2)

    try:
        sheet = pygame.image.load(sprite_path).convert_alpha()
    except Exception:
        return {k: [fallback.copy()] for k in ("down", "left", "right", "up")}

    sw, sh = sheet.get_size()

    # Pixel Crawler run sheets come as one row (e.g. 384x64 => 6x1 frames).
    if sw % 6 == 0 and sh <= (sw // 6):
        cols = 6
        rows = 1
    elif sh % 4 == 0 and sw % 6 == 0 and (sw // 6) >= (sh // 4):
        cols = 6
        rows = 4
    elif sh % 4 == 0 and sw % 4 == 0:
        cols = 4
        rows = 4
    else:
        cols = max(1, round(sw / max(1, sh)))
        rows = 1

    frame_w = max(1, sw // cols)
    frame_h = max(1, sh // rows)

    if rows == 1:
        run_frames = _extract_frames(sheet, 0, cols, frame_w, frame_h, fallback)[:6]
        left_frames = [pygame.transform.flip(frame, True, False) for frame in run_frames]
        return {
            "down": [frame.copy() for frame in run_frames],
            "up": [frame.copy() for frame in run_frames],
            "right": [frame.copy() for frame in run_frames],
            "left": left_frames,
        }

    row_map = {"down": 0, "left": 1, "right": 2, "up": 3}
    frames: dict[str, list[pygame.Surface]] = {}
    max_frames = 6 if cols >= 6 else 4
    for direction, row in row_map.items():
        direction_frames = _extract_frames(sheet, row, cols, frame_w, frame_h, fallback)
        frames[direction] = direction_frames[:max_frames]
    return frames


class EnemyProjectile(pygame.sprite.Sprite):
    def __init__(
        self,
        x: float,
        y: float,
        direction: pygame.Vector2,
        damage: float,
        groups=(),
        speed: float = ENEMY_BULLET_SPEED,
        collision_mask=None,
        dynamic_collision_getter=None,
        map_bounds=None,
    ):
        if isinstance(groups, (tuple, list)):
            super().__init__(*groups)
        else:
            super().__init__(groups)

        size = 8
        self.image = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(self.image, (255, 120, 60), (size // 2, size // 2), size // 2)
        self.rect = self.image.get_rect(center=(int(x), int(y)))
        self._mask = pygame.mask.from_surface(self.image)
        self._pos = pygame.Vector2(float(x), float(y))
        self._vel = _safe_normalize(pygame.Vector2(direction)) * float(speed)
        if self._vel.length_squared() <= 1e-9:
            self._vel = pygame.Vector2(0.0, 1.0) * float(speed)
        self.damage = float(damage)
        self._collision_mask = collision_mask
        self._dynamic_collision_getter = dynamic_collision_getter
        self._map_bounds = map_bounds if map_bounds is not None else pygame.Rect(0, 0, 9999, 9999)

    def _hits_static(self) -> bool:
        if self._collision_mask is not None:
            return self._collision_mask.overlap(self._mask, (self.rect.x, self.rect.y)) is not None
        return False

    def _hits_dynamic(self) -> bool:
        if not callable(self._dynamic_collision_getter):
            return False
        for rect in self._dynamic_collision_getter() or ():
            if self.rect.colliderect(rect):
                return True
        return False

    def update(self):
        distance = max(1, int(math.ceil(self._vel.length())))
        step = self._vel / float(distance)
        for _ in range(distance):
            self._pos += step
            self.rect.center = (int(self._pos.x), int(self._pos.y))
            if self._hits_static() or self._hits_dynamic():
                self.kill()
                return
        if not self._map_bounds.contains(self.rect):
            self.kill()


class BaseEnemy(pygame.sprite.Sprite):
    enemy_code = "?"

    def __init__(
        self,
        x: int,
        y: int,
        groups=(),
        speed: float = 1.5,
        max_health: int = 60,
        melee_damage: int = 10,
        ranged_damage: int = 10,
        vision_range: float = 200.0,
        can_seek_potion: bool = False,
    ):
        if isinstance(groups, (tuple, list)):
            super().__init__(*groups)
        else:
            super().__init__(groups)

        self.speed = float(speed)
        self.max_health = int(max(1, max_health))
        self.health = float(self.max_health)
        self.melee_damage = int(max(1, melee_damage))
        self.ranged_damage = int(max(1, ranged_damage))
        self.vision_range = float(vision_range)
        self.can_seek_potion = bool(can_seek_potion)

        sprite_path = _resolve_sprite_path(MONSTER_SPRITES_BY_TYPE.get(self.enemy_code, ""))
        self.frames = _load_sheet_frames(sprite_path)
        self.direction = "down"
        self._frame = 0.0
        self._anim_speed = 0.18
        self.image = self.frames[self.direction][0].copy()
        self.rect = self.image.get_rect(center=(int(x), int(y)))

        self.hitbox = self.rect.inflate(-int(self.rect.width * 0.46), -int(self.rect.height * 0.46))
        self._pos = pygame.Vector2(float(self.hitbox.centerx), float(self.hitbox.centery))
        self._hitbox_mask = pygame.mask.Mask((self.hitbox.width, self.hitbox.height), fill=True)
        self._last_dx = 0.0
        self._last_dy = 0.0

        self.state = "IDLE"
        self.defending = False
        self._hit_flash_until = 0
        self._melee_cd = 0
        self._ranged_cd = 0
        self._decision_timer = 0
        self._idle_wander_target: pygame.Vector2 | None = None
        self.debug_path_points: list[tuple[float, float]] = []
        self.last_sensors = {
            "dist_norm": 1.0,
            "hp_norm": 1.0,
            "potion_visible": 0.0,
            "vision": 0.0,
            "ranged_cd_norm": 0.0,
        }

    @property
    def low_hp(self) -> bool:
        return (self.health / max(1.0, float(self.max_health))) <= ENEMY_LOW_HP_RATIO

    def take_damage(self, amount: float):
        if not self.alive():
            return
        damage = float(amount)
        if self.defending:
            damage *= 0.35
        self.health = max(0.0, self.health - damage)
        self._hit_flash_until = pygame.time.get_ticks() + 110
        if self.health <= 0:
            self.kill()

    def heal(self, amount: float):
        self.health = min(float(self.max_health), self.health + float(amount))

    def _update_animation(self, moving: bool):
        frames = self.frames[self.direction]
        if moving:
            self._frame = (self._frame + self._anim_speed) % float(len(frames))
        else:
            self._frame = 0.0
        self.image = frames[int(self._frame)]
        if pygame.time.get_ticks() < self._hit_flash_until:
            tinted = self.image.copy()
            flash = pygame.Surface(tinted.get_size(), pygame.SRCALPHA)
            flash.fill((255, 110, 110, 100))
            tinted.blit(flash, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            self.image = tinted
        self.rect = self.image.get_rect(center=self.hitbox.center)

    def _resolve_collisions(self, axis: str, game_map):
        dynamic_rects = game_map.get_dynamic_collisions() if game_map else []
        for rect in dynamic_rects:
            if self.hitbox.colliderect(rect):
                if axis == "x":
                    if self._last_dx > 0:
                        self.hitbox.right = min(self.hitbox.right, rect.left)
                    elif self._last_dx < 0:
                        self.hitbox.left = max(self.hitbox.left, rect.right)
                else:
                    if self._last_dy > 0:
                        self.hitbox.bottom = min(self.hitbox.bottom, rect.top)
                    elif self._last_dy < 0:
                        self.hitbox.top = max(self.hitbox.top, rect.bottom)

        collision_mask = getattr(game_map, "collision_mask", None)
        if collision_mask is not None:
            if collision_mask.overlap(self._hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                if axis == "x":
                    step = -1 if self._last_dx > 0 else 1
                    for _ in range(14):
                        if not collision_mask.overlap(self._hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                            break
                        self.hitbox.x += step
                else:
                    step = -1 if self._last_dy > 0 else 1
                    for _ in range(14):
                        if not collision_mask.overlap(self._hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                            break
                        self.hitbox.y += step

    def _move_vector(self, move: pygame.Vector2, game_map) -> bool:
        if move.length_squared() <= 1e-9:
            return False
        direction = _safe_normalize(move)
        if direction.length_squared() <= 1e-9:
            return False

        self.direction = _direction_from_vector(direction)

        vx = direction.x * self.speed
        vy = direction.y * self.speed

        self._last_dx = vx
        self._pos.x += vx
        self.hitbox.centerx = round(self._pos.x)
        self._resolve_collisions("x", game_map)
        self._pos.x = float(self.hitbox.centerx)

        self._last_dy = vy
        self._pos.y += vy
        self.hitbox.centery = round(self._pos.y)
        self._resolve_collisions("y", game_map)
        self._pos.y = float(self.hitbox.centery)

        self.rect.center = self.hitbox.center
        return True

    def _move_toward(self, tx: float, ty: float, game_map) -> bool:
        return self._move_vector(pygame.Vector2(float(tx) - self._pos.x, float(ty) - self._pos.y), game_map)

    def _move_away(self, tx: float, ty: float, game_map) -> bool:
        return self._move_vector(pygame.Vector2(self._pos.x - float(tx), self._pos.y - float(ty)), game_map)

    def _try_melee(self, player) -> bool:
        if self._melee_cd > 0:
            return False
        if self._pos.distance_to(pygame.Vector2(player.hitbox.center)) > ENEMY_MELEE_RANGE:
            return False
        self._melee_cd = 42
        player.take_damage(self.melee_damage)
        return True

    def _try_ranged(self, player, game_map, enemy_projectile_group) -> bool:
        if self._ranged_cd > 0:
            return False
        vec = pygame.Vector2(float(player.hitbox.centerx) - self._pos.x, float(player.hitbox.centery) - self._pos.y)
        direction = _safe_normalize(vec)
        if direction.length_squared() <= 1e-9:
            return False
        self._ranged_cd = 70
        self.direction = _direction_from_vector(direction)
        EnemyProjectile(
            x=self._pos.x,
            y=self._pos.y,
            direction=direction,
            damage=self.ranged_damage,
            groups=(enemy_projectile_group,),
            speed=ENEMY_BULLET_SPEED,
            collision_mask=getattr(game_map, "collision_mask", None),
            dynamic_collision_getter=(game_map.get_dynamic_collisions if game_map else None),
            map_bounds=(
                pygame.Rect(0, 0, int(game_map.map_width), int(game_map.map_height))
                if game_map is not None
                else pygame.Rect(0, 0, 9999, 9999)
            ),
        )
        return True

    def _seek_health_potion(self, item_manager, game_map) -> bool:
        if not self.can_seek_potion or item_manager is None:
            return False
        targets = item_manager.get_active_potion_positions(("vida",))
        if not targets:
            return False
        _, nearest = min(targets, key=lambda item: self._pos.distance_to(item[1]))
        self.debug_path_points = [(float(nearest.x), float(nearest.y))]
        self.state = "HEAL"
        moved = self._move_toward(nearest.x, nearest.y, game_map)
        consumed = item_manager.consume_potion_at(
            world_x=self._pos.x,
            world_y=self._pos.y,
            radius=float(max(self.hitbox.width, self.hitbox.height) * 0.75),
            potion_types=("vida",),
        )
        if consumed == "vida":
            self.heal(35)
        return moved

    def _update_sensors(self, player, item_manager):
        player_dist = self._pos.distance_to(pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery)))
        potions = item_manager.get_active_potion_positions(("vida",)) if item_manager else []
        potion_visible = 0.0
        if potions:
            nearest_p = min(potions, key=lambda item: self._pos.distance_to(item[1]))[1]
            if self._pos.distance_to(nearest_p) <= self.vision_range:
                potion_visible = 1.0

        self.last_sensors = {
            "dist_norm": min(1.0, player_dist / 400.0),
            "hp_norm": self.health / max(1.0, float(self.max_health)),
            "potion_visible": potion_visible,
            "vision": 1.0 if player_dist <= self.vision_range else 0.0,
            "ranged_cd_norm": min(1.0, self._ranged_cd / 70.0),
        }

    def _idle_wander(self, game_map):
        self.state = "IDLE"
        self.debug_path_points = []
        self._decision_timer -= 1
        if self._decision_timer <= 0 or self._idle_wander_target is None:
            self._decision_timer = random.randint(40, 100)
            offset = pygame.Vector2(random.uniform(-80, 80), random.uniform(-80, 80))
            self._idle_wander_target = pygame.Vector2(self._pos.x + offset.x, self._pos.y + offset.y)
        if self._idle_wander_target is None:
            return False
        if self._pos.distance_to(self._idle_wander_target) < 8:
            return False
        self.debug_path_points = [(float(self._idle_wander_target.x), float(self._idle_wander_target.y))]
        return self._move_toward(self._idle_wander_target.x, self._idle_wander_target.y, game_map)

    def _update_behavior(self, player, game_map, item_manager, enemy_projectile_group) -> bool:
        return self._idle_wander(game_map)

    def update(self, player, game_map, item_manager, enemy_projectile_group):
        if not self.alive():
            return

        self.defending = False
        if self._melee_cd > 0:
            self._melee_cd -= 1
        if self._ranged_cd > 0:
            self._ranged_cd -= 1

        self._update_sensors(player, item_manager)
        moved = self._update_behavior(player, game_map, item_manager, enemy_projectile_group)
        self._update_animation(moving=moved)


class EnemyTypeA(BaseEnemy):
    enemy_code = "A"

    def __init__(self, x: int, y: int, groups=()):
        super().__init__(
            x=x,
            y=y,
            groups=groups,
            speed=ENEMY_A_SPEED,
            max_health=ENEMY_A_HEALTH,
            melee_damage=ENEMY_A_DAMAGE,
            ranged_damage=0,
            vision_range=ENEMY_A_VISION_RANGE,
            can_seek_potion=True,
        )

    def _update_behavior(self, player, game_map, item_manager, enemy_projectile_group) -> bool:
        dist = self._pos.distance_to(pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery)))
        if self.low_hp and self._seek_health_potion(item_manager, game_map):
            return True
        if dist <= self.vision_range:
            self.state = "CHASE" if dist > ENEMY_MELEE_RANGE else "ATTACK"
            self.debug_path_points = [(float(player.hitbox.centerx), float(player.hitbox.centery))]
            self._try_melee(player)
            return self._move_toward(player.hitbox.centerx, player.hitbox.centery, game_map)
        return self._idle_wander(game_map)


class EnemyTypeB(BaseEnemy):
    enemy_code = "B"

    def __init__(self, x: int, y: int, groups=()):
        super().__init__(
            x=x,
            y=y,
            groups=groups,
            speed=ENEMY_B_SPEED,
            max_health=ENEMY_B_HEALTH,
            melee_damage=0,
            ranged_damage=ENEMY_B_DAMAGE,
            vision_range=ENEMY_B_VISION_RANGE,
            can_seek_potion=False,
        )

    def _update_behavior(self, player, game_map, item_manager, enemy_projectile_group) -> bool:
        dist = self._pos.distance_to(pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery)))
        self.debug_path_points = [(float(player.hitbox.centerx), float(player.hitbox.centery))]
        if dist <= self.vision_range:
            if dist <= ENEMY_CLOSE_RANGE:
                self.state = "DEFEND"
                self.defending = True
                return False
            self.state = "RANGED"
            self._try_ranged(player, game_map, enemy_projectile_group)
            return False
        return False


class EnemyTypeC(BaseEnemy):
    enemy_code = "C"

    def __init__(self, x: int, y: int, groups=()):
        super().__init__(
            x=x,
            y=y,
            groups=groups,
            speed=ENEMY_C_SPEED,
            max_health=ENEMY_C_HEALTH,
            melee_damage=ENEMY_A_DAMAGE,
            ranged_damage=ENEMY_C_DAMAGE,
            vision_range=ENEMY_C_VISION_RANGE,
            can_seek_potion=True,
        )

    def _update_behavior(self, player, game_map, item_manager, enemy_projectile_group) -> bool:
        player_center = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
        dist = self._pos.distance_to(player_center)
        if self.low_hp and self._seek_health_potion(item_manager, game_map):
            return True

        if dist <= self.vision_range:
            self.debug_path_points = [(float(player_center.x), float(player_center.y))]
            if dist <= ENEMY_MELEE_RANGE:
                self.state = "COUNTER"
                self._try_melee(player)
                return self._move_away(player_center.x, player_center.y, game_map)
            if dist <= ENEMY_C_FLEE_RANGE:
                self.state = "FLEE"
                return self._move_away(player_center.x, player_center.y, game_map)
            self.state = "RANGED"
            self._try_ranged(player, game_map, enemy_projectile_group)
            return False
        return self._idle_wander(game_map)


# Compatibilidad: se deja el nombre viejo como alias del Tipo A.
PlaceholderEnemy = EnemyTypeA
