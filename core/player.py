# ============================================================
#  core/player.py  –  Jugador con movimiento, animación y acciones
# ============================================================
# Espera un spritesheet del Ninja Adventure Pack con este layout:
#   Fila 0 → Walk Down   (N frames)
#   Fila 1 → Walk Left
#   Fila 2 → Walk Right
#   Fila 3 → Walk Up
#   Fila 4 → Idle (todas las direcciones, o solo 1 frame por dir)
#
# Si tu spritesheet tiene un layout distinto, ajusta ANIM_ROWS.
# ============================================================

import math
import pygame
import os
from config.settings import (
    PLAYER_SPEED, PLAYER_MAX_HEALTH, PLAYER_MAX_SHIELD, PLAYER_MAX_ENERGY,
    PLAYER_ATTACK_DMGM, PLAYER_ATTACK_DMGR,
    PLAYER_BULLET_SPEED,
    PLAYER_RANGED_MANA_COST,
    SPRITES_DIR, TILE_SIZE
)

# ── Configuración del spritesheet ────────────────────────────
SPRITE_W      = 16      # ancho de 1 frame en el PNG original
SPRITE_H      = 16      # alto  de 1 frame en el PNG original
SPRITE_SCALE  = 2.25    # Aumentado para que el personaje se vea mas grande e imponente
FRAME_COUNT   = 4       # cuántos frames de animación por dirección
ANIM_SPEED    = 8       # frames de juego entre cada frame de animación

# Fila del spritesheet por dirección
ANIM_ROWS = {
    "down":  0,
    "left":  1,
    "right": 2,
    "up":    3,
}

# ── Proyectil simple ──────────────────────────────────────────
class Bullet(pygame.sprite.Sprite):
    SPEED  = PLAYER_BULLET_SPEED
    DAMAGE = PLAYER_ATTACK_DMGR
    COLOR  = (255, 220, 50)

    def __init__(
        self,
        x,
        y,
        dx,
        dy,
        groups,
        collision_rects,
        collision_mask=None,
        dynamic_collision_getter=None,
        map_bounds=None,
    ):
        super().__init__(groups)
        self.image = pygame.Surface((8, 8), pygame.SRCALPHA)
        pygame.draw.circle(self.image, self.COLOR, (4, 4), 4)
        self.rect           = self.image.get_rect(center=(x, y))
        self._pos           = pygame.math.Vector2(x, y)
        self._vel           = pygame.math.Vector2(dx, dy).normalize() * self.SPEED
        self._col_rects     = collision_rects
        self._col_mask      = collision_mask
        self._dynamic_col_getter = dynamic_collision_getter
        self._map_bounds    = map_bounds if map_bounds is not None else pygame.Rect(0, 0, 9999, 9999)
        self._self_mask     = pygame.mask.from_surface(self.image)
        self.damage         = self.DAMAGE

    def _hits_static_collision(self) -> bool:
        if self._col_mask is not None:
            return self._col_mask.overlap(self._self_mask, (self.rect.x, self.rect.y)) is not None
        for r in self._col_rects:
            if self.rect.colliderect(r):
                return True
        return False

    def _hits_dynamic_collision(self) -> bool:
        if not callable(self._dynamic_col_getter):
            return False
        for rect in self._dynamic_col_getter() or ():
            if self.rect.colliderect(rect):
                return True
        return False

    def update(self, *args, **kwargs):
        distance = max(1, int(math.ceil(self._vel.length())))
        step = self._vel / float(distance)

        for _ in range(distance):
            self._pos += step
            self.rect.center = (int(self._pos.x), int(self._pos.y))

            # Destruir si choca con pared/poligono
            if self._hits_static_collision() or self._hits_dynamic_collision():
                self.kill()
                return

        # Destruir si sale del mapa
        if not self._map_bounds.contains(self.rect):
            self.kill()


# ── Jugador ───────────────────────────────────────────────────
class Player(pygame.sprite.Sprite):

    def __init__(self, x: int, y: int,
                 groups: tuple,
                 collision_rects: list[pygame.Rect],
                 bullet_group: pygame.sprite.Group,
                 sprite_path: str | None = None,
                 collision_mask: pygame.mask.Mask | None = None):
        super().__init__(groups)

        self.collision_rects = collision_rects
        self.bullet_group    = bullet_group

        # ── Stats ─────────────────────────────────────────────
        self.max_health = PLAYER_MAX_HEALTH
        self.health     = PLAYER_MAX_HEALTH
        self.max_shield = PLAYER_MAX_SHIELD
        self.shield     = PLAYER_MAX_SHIELD
        self.max_energy = PLAYER_MAX_ENERGY
        self.energy     = PLAYER_MAX_ENERGY
        self.ranged_mana_cost = float(PLAYER_RANGED_MANA_COST)
        self.speed      = PLAYER_SPEED
        self.alive      = True

        # ── Cooldowns ─────────────────────────────────────────
        self._melee_cd    = 0
        self._ranged_cd   = 0
        self._defend_cd   = 0
        self.is_defending = False
        self.shield_broken = False

        # ── Animación y Estados ───────────────────────────────
        self.state        = "idle"
        self.direction    = "down"
        self._frame_index = 0
        self._anim_timer  = 0
        self._moving      = False

        self.animations = {
            "idle": self._load_animation_folder("idle"),
            "walk": self._load_animation_folder("walk"),
            "attack": self._load_animation_folder("attack"),
            "shoot": self._load_animation_folder("attack"), # Reusar sprite de melee para evitar problemas de orientacion
            "defend": self._load_animation_folder("defend"),
            "hit": self._load_animation_folder("hit"),
            "death": self._load_animation_folder("death"),
        }
        
        # Fallback si death/hit solo se parsearon en down (en assets genéricos a veces es 1 sola fila)
        for k in ["hit", "death"]:
            if self.animations[k]["down"]:
                for d in ["up", "left", "right"]:
                    if not self.animations[k][d]:
                        self.animations[k][d] = self.animations[k]["down"]
                        
        # Dummy fill si falta algo
        for k in self.animations:
            for d in self.animations[k]:
                if not self.animations[k][d]:
                    sf = pygame.Surface((int(SPRITE_W * SPRITE_SCALE), int(SPRITE_H * SPRITE_SCALE)), pygame.SRCALPHA)
                    sf.fill((255, 0, 255))
                    self.animations[k][d].append(sf)

        # ── Imagen y rect ─────────────────────────────────────
        self.image = self.animations[self.state][self.direction][0]
        self.rect  = self.image.get_rect(topleft=(x, y))
        
        # Hitbox (caja de colisión) un 70% más pequeña para dar máxima tolerancia y libertad de movimiento
        self.hitbox = self.rect.inflate(-int(self.rect.width * 0.65), -int(self.rect.height * 0.75))
        self._pos  = pygame.math.Vector2(self.hitbox.centerx, self.hitbox.centery)
        self._last_dx = 0
        self._last_dy = 0
        
        self.collision_mask = collision_mask
        self._last_hazard_damage_ms = 0
        self.hazard_hits = 0
        if self.collision_mask:
            surf = pygame.Surface((self.hitbox.width, self.hitbox.height), pygame.SRCALPHA)
            surf.fill((255, 255, 255, 255))
            self.hitbox_mask = pygame.mask.from_surface(surf)

    # ── Carga de animaciones separadas ─────────────────────────
    def _load_animation_folder(self, action: str) -> dict:
        frames = {"down": [], "up": [], "left": [], "right": []}
        base_dir = os.path.join("assets", "player", "separate", action)
        
        if not os.path.exists(base_dir):
            # Fallback en caso de que esté usando mayúsculas en 'Separate' en su OS
            base_dir = os.path.join("assets", "player", "Separate", action)
            if not os.path.exists(base_dir):
                return frames
            
        for d in frames.keys():
            i = 0
            while True:
                path = os.path.join(base_dir, f"{action}_{d}_{i}.png")
                if os.path.exists(path):
                    frame = pygame.image.load(path).convert_alpha()
                    frame = pygame.transform.scale(
                        frame,
                        (int(SPRITE_W * SPRITE_SCALE), int(SPRITE_H * SPRITE_SCALE))
                    )
                    frames[d].append(frame)
                    i += 1
                else:
                    break
        return frames

    # ── Update principal ──────────────────────────────────────
    def update(self, keys, enemies=None, game_map=None, *args, **kwargs):
        if not self.alive:
            self.state = "death"
            self._moving = False
            self._update_animation()
            return

        # Decrementar cooldowns
        if self._melee_cd  > 0: self._melee_cd  -= 1
        if self._ranged_cd > 0: self._ranged_cd -= 1

        # Check action locks (acciones que bloquean controles temporalmente)
        action_locked = self.state in ["attack", "shoot", "hit", "defend"]

        # Escudo / Defensa (Mantenimiento continuo o accion fija)
        # Si ya abrimos el escudo y lo mantenemos apretado:
        if self.state == "defend" and keys[pygame.K_SPACE]:
            self._start_defend() # gasta sobre tiempo
            if self.shield <= 0:
                self.shield_broken = True  # Escudo roto, necesita regenerar 30% antes de usar otra vez
                self.state = "idle"
                self.is_defending = False
                action_locked = False
        # Si iniciamos el escudo desde 0
        elif keys[pygame.K_SPACE] and not action_locked and self.shield > 0 and not self.shield_broken:
            self.state = "defend"
            self._frame_index = 0
            self._start_defend()
            action_locked = True
        # Si lo soltamos
        elif self.state == "defend" and not keys[pygame.K_SPACE]:
            self.state = "idle"
            self.is_defending = False
            action_locked = False
        else:
            # Regenar escudo pasivamente
            if self.shield < self.max_shield and self.state != "defend":
                self.shield = min(self.max_shield, self.shield + 0.1)
                # Si estaba roto, rehabilitar al alcanzar el 30%
                if self.shield_broken and self.shield >= self.max_shield * 0.3:
                    self.shield_broken = False
                    
        # Regenerar energia pasivamente siempre
        if self.energy < self.max_energy:
            self.energy = min(self.max_energy, self.energy + 0.05)

        if not action_locked:
            # Check inputs accionables prioritarios
            if keys[pygame.K_z] and self._melee_cd == 0:
                self.state = "attack"
                self._frame_index = 0
                self._anim_timer = 0
                self._melee_attack(enemies)
                action_locked = True
            elif keys[pygame.K_x] and self._ranged_cd == 0 and self.energy >= self.ranged_mana_cost:
                self.state = "shoot"
                self._frame_index = 0
                self._anim_timer = 0
                self.energy -= self.ranged_mana_cost
                self._ranged_attack(game_map, enemies=enemies)
                action_locked = True
        
        # Movimiento base si no estamos atacando/bloqueados
        if not action_locked:
            dx, dy = 0, 0
            if keys[pygame.K_w] or keys[pygame.K_UP]:    dy -= 1; self.direction = "up"
            if keys[pygame.K_s] or keys[pygame.K_DOWN]:  dy += 1; self.direction = "down"
            if keys[pygame.K_a] or keys[pygame.K_LEFT]:  dx -= 1; self.direction = "left"
            if keys[pygame.K_d] or keys[pygame.K_RIGHT]: dx += 1; self.direction = "right"

            self._moving = (dx != 0 or dy != 0)
            if self._moving:
                self.state = "walk"
                self._move(dx, dy, game_map)
                if game_map:
                    self._check_hazards(game_map)
            else:
                self.state = "idle"

        self._update_animation()

    # ── Movimiento con colisión ───────────────────────────────
    def _move(self, dx: int, dy: int, game_map=None):
        # Normalizar diagonal
        vec = pygame.math.Vector2(dx, dy)
        if vec.length() > 0:
            vec = vec.normalize() * self.speed
            
        dynamic_rects = game_map.get_dynamic_collisions() if game_map else []

        # Eje X
        self._last_dx = vec.x
        self._pos.x += vec.x
        self.hitbox.centerx = round(self._pos.x)
        self._resolve_collisions("x", dynamic_rects)
        self._pos.x = self.hitbox.centerx

        # Eje Y
        self._last_dy = vec.y
        self._pos.y += vec.y
        self.hitbox.centery = round(self._pos.y)
        self._resolve_collisions("y", dynamic_rects)
        self._pos.y = self.hitbox.centery

        # Actualizar la posición de dibujado según el hitbox
        self.rect.center = self.hitbox.center

    def _resolve_collisions(self, axis: str, dynamic_rects: list[pygame.Rect] = None):
        if dynamic_rects is None: dynamic_rects = []
        
        # 1. Colisiones AABB para objetos dinamicos (Puertas cerradas, cofres)
        for rect in dynamic_rects:
            if self.hitbox.colliderect(rect):
                if axis == "x":
                    if self._last_dx > 0 and self.hitbox.right > rect.left and self.hitbox.left < rect.left:
                        self.hitbox.right = rect.left
                    elif self._last_dx < 0 and self.hitbox.left < rect.right and self.hitbox.right > rect.right:
                        self.hitbox.left = rect.right
                elif axis == "y":
                    if self._last_dy > 0 and self.hitbox.bottom > rect.top and self.hitbox.top < rect.top:
                        self.hitbox.bottom = rect.top
                    elif self._last_dy < 0 and self.hitbox.top < rect.bottom and self.hitbox.bottom > rect.bottom:
                        self.hitbox.top = rect.bottom

        if self.collision_mask:
            # Colisión fluida con pixel-perfect Masks (Permite Diagonal y Triángulos exactos)
            if self.collision_mask.overlap(self.hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                if axis == "x":
                    if self._last_dx > 0:
                        while self.collision_mask.overlap(self.hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                            self.hitbox.x -= 1
                    elif self._last_dx < 0:
                        while self.collision_mask.overlap(self.hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                            self.hitbox.x += 1
                elif axis == "y":
                    if self._last_dy > 0:
                        while self.collision_mask.overlap(self.hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                            self.hitbox.y -= 1
                    elif self._last_dy < 0:
                        while self.collision_mask.overlap(self.hitbox_mask, (self.hitbox.x, self.hitbox.y)):
                            self.hitbox.y += 1
        else:
            # Fallback a rectángulos (AABB Clásico)
            for rect in self.collision_rects:
                if self.hitbox.colliderect(rect):
                    if axis == "x":
                        if self.hitbox.right > rect.left and self.hitbox.left < rect.left:
                            self.hitbox.right = rect.left
                        elif self.hitbox.left < rect.right:
                            self.hitbox.left  = rect.right
                    else:
                        if self.hitbox.bottom > rect.top and self.hitbox.top < rect.top:
                            self.hitbox.bottom = rect.top
                        elif self.hitbox.top < rect.bottom:
                            self.hitbox.top    = rect.bottom

    def _check_hazards(self, game_map):
        hazard_rects = getattr(game_map, "hazard_rects", [])
        if not hazard_rects:
            return

        now = pygame.time.get_ticks()
        if now - self._last_hazard_damage_ms < 500:
            return

        for rect in hazard_rects:
            if self.hitbox.colliderect(rect):
                self._last_hazard_damage_ms = now
                self.hazard_hits += 1
                # Hongos: daño fuerte por contacto (50% de la vida máxima).
                self.take_damage(int(self.max_health * 0.5))
                break

    # ── Animación ─────────────────────────────────────────────
    def _update_animation(self):
        frames_list = self.animations[self.state][self.direction]
        total_frames = len(frames_list)
        
        self._anim_timer += 1
        speed_factor = ANIM_SPEED
        if self.state in ["attack", "shoot", "hit", "death"]:
            speed_factor = 5  # Animaciones de accion/combate son ligeramente más rapidas

        if self._anim_timer >= speed_factor:
            self._anim_timer = 0
            
            # El Idle no debe dar vueltas para no temblar y Defend debe ser estatico si es un frame
            if self.state == "idle" or self.state == "defend":
                self._frame_index = 0
            else:
                self._frame_index += 1

            if self._frame_index >= total_frames:
                # Loop o terminación de estado
                if self.state in ["attack", "shoot", "hit"]:
                    self.state = "idle"  # Desbloquea y vuelve a idle
                    self._frame_index = 0
                    frames_list = self.animations[self.state][self.direction]
                elif self.state == "death":
                    self._frame_index = total_frames - 1  # Se queda muerto en el piso
                else:
                    # Idle / Walk (Loop normal)
                    self._frame_index = 0

        # Safety check
        if self._frame_index >= len(frames_list):
            self._frame_index = 0

        self.image = frames_list[self._frame_index]

    # ── Acciones ──────────────────────────────────────────────
    def _melee_attack(self, enemies):
        self._melee_cd = 40
        if not enemies:
            return
        reach = float(TILE_SIZE * 1.28)
        forward = {
            "down": pygame.math.Vector2(0.0, 1.0),
            "up": pygame.math.Vector2(0.0, -1.0),
            "left": pygame.math.Vector2(-1.0, 0.0),
            "right": pygame.math.Vector2(1.0, 0.0),
        }.get(self.direction, pygame.math.Vector2(0.0, 1.0))
        player_center = pygame.math.Vector2(float(self.hitbox.centerx), float(self.hitbox.centery))
        for enemy in enemies:
            enemy_hitbox = getattr(enemy, "hitbox", enemy.rect)
            enemy_center = pygame.math.Vector2(float(enemy_hitbox.centerx), float(enemy_hitbox.centery))
            to_enemy = enemy_center - player_center
            distance = float(to_enemy.length())
            if distance > reach:
                continue
            if distance > 1e-6:
                facing = to_enemy.normalize().dot(forward)
                if facing < 0.12:
                    continue
            enemy.take_damage(PLAYER_ATTACK_DMGM)

    def fire_ranged_at(self, target_world_x: float, target_world_y: float, game_map=None, enemies=None) -> bool:
        if not self.alive:
            return False
        if self.state in ("attack", "shoot", "hit", "defend"):
            return False
        if self._ranged_cd > 0 or self.energy < self.ranged_mana_cost:
            return False

        aim = pygame.math.Vector2(
            float(target_world_x) - float(self.rect.centerx),
            float(target_world_y) - float(self.rect.centery),
        )
        if aim.length_squared() <= 1e-6:
            return False

        # Actualiza la direccion para mantener coherencia de animaciones.
        if abs(aim.x) >= abs(aim.y):
            self.direction = "right" if aim.x >= 0 else "left"
        else:
            self.direction = "down" if aim.y >= 0 else "up"

        self.state = "shoot"
        self._frame_index = 0
        self._anim_timer = 0
        self.energy -= self.ranged_mana_cost
        self._ranged_attack(game_map, direction_vec=aim.normalize(), enemies=enemies)
        return True

    def _apply_point_blank_ranged_damage(self, direction_vec: pygame.math.Vector2, enemies) -> bool:
        if not enemies:
            return False

        origin = pygame.math.Vector2(float(self.hitbox.centerx), float(self.hitbox.centery))
        close_rect = self.hitbox.inflate(14, 14)
        close_radius = float(max(12, int(min(self.hitbox.width, self.hitbox.height) * 0.95)))
        forward = direction_vec.normalize() if direction_vec.length_squared() > 1e-6 else pygame.math.Vector2(0.0, 1.0)
        hit_any = False

        for enemy in enemies:
            enemy_hitbox = getattr(enemy, "hitbox", enemy.rect)
            enemy_center = pygame.math.Vector2(float(enemy_hitbox.centerx), float(enemy_hitbox.centery))
            to_enemy = enemy_center - origin
            dist = float(to_enemy.length())
            if dist > (close_radius * 1.8):
                continue
            if not enemy_hitbox.colliderect(close_rect):
                continue
            if dist > 1e-6 and to_enemy.normalize().dot(forward) < -0.15:
                continue
            enemy.take_damage(PLAYER_ATTACK_DMGR)
            hit_any = True
        return hit_any

    def _ranged_attack(self, game_map=None, direction_vec: pygame.math.Vector2 | None = None, enemies=None):
        self._ranged_cd = 30

        if direction_vec is None:
            offsets = {"down": (0, 1), "up": (0, -1), "left": (-1, 0), "right": (1, 0)}
            dx, dy = offsets[self.direction]
            direction_vec = pygame.math.Vector2(float(dx), float(dy))
        else:
            direction_vec = pygame.math.Vector2(direction_vec)

        if direction_vec.length_squared() <= 1e-6:
            direction_vec = pygame.math.Vector2(0.0, 1.0)
        else:
            direction_vec = direction_vec.normalize()

        # A quemarropa, el rayo aplica dano desde la hitbox del heroe.
        self._apply_point_blank_ranged_damage(direction_vec, enemies)

        dynamic_collision_getter = game_map.get_dynamic_collisions if game_map else None
        map_bounds = (
            pygame.Rect(0, 0, int(game_map.map_width), int(game_map.map_height))
            if game_map is not None
            else pygame.Rect(0, 0, 9999, 9999)
        )
        Bullet(
            self.rect.centerx, self.rect.centery,
            float(direction_vec.x), float(direction_vec.y),
            (self.bullet_group,),
            self.collision_rects,
            collision_mask=self.collision_mask,
            dynamic_collision_getter=dynamic_collision_getter,
            map_bounds=map_bounds,
        )

    def _start_defend(self):
        self.is_defending = True
        if self.shield > 0:
            self.shield = max(0, self.shield - 0.8)  # Gasta 0.8 por frame (~2 segundos para vaciar 100 de aguante)

    # ── Recibir daño ──────────────────────────────────────────
    def take_damage(self, amount: int):
        if not self.alive:
            return

        incoming = max(0.0, float(amount))
        if incoming <= 0.0:
            return

        # El escudo siempre absorbe una parte; defendiendo absorbe mas.
        if self.shield > 0.0:
            absorb_ratio = 1.0 if self.is_defending else 0.70
            absorbed = min(float(self.shield), incoming * absorb_ratio)
            self.shield = max(0.0, float(self.shield) - absorbed)
            incoming = max(0.0, incoming - absorbed)
            if self.shield <= 0.0:
                self.shield_broken = True

        # Defensa activa: reduce tambien el dano residual.
        if self.is_defending and incoming > 0.0:
            incoming *= 0.55

        final_damage = int(max(0, round(incoming)))
        self.health = max(0, self.health - final_damage)
        self.state = "hit"   # trigger knockback/hit anim
        self._frame_index = 0
        self._anim_timer = 0
        
        if self.health <= 0:
            self.alive = False
            self.state = "death"
            self._frame_index = 0
            self._anim_timer = 0

    def heal(self, amount: int):
        self.health = min(self.max_health, self.health + amount)
