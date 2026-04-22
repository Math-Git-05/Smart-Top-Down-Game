from __future__ import annotations

from dataclasses import dataclass
import random

import pygame

from ai.genetic_algorithm import Genome, default_genome


@dataclass(slots=True)
class AgentDecision:
    move_x: float = 0.0
    move_y: float = 0.0
    melee: bool = False
    defend: bool = False
    ranged_target: tuple[float, float] | None = None


class VirtualKeys:
    """Lightweight key-state object compatible with Player.update(keys)."""

    def __init__(self, pressed: set[int] | None = None):
        self._pressed = pressed or set()

    def __getitem__(self, key_code: int) -> bool:
        return key_code in self._pressed


def decision_to_keys(decision: AgentDecision) -> VirtualKeys:
    pressed: set[int] = set()

    if decision.move_y < -0.22:
        pressed.add(pygame.K_w)
        pressed.add(pygame.K_UP)
    elif decision.move_y > 0.22:
        pressed.add(pygame.K_s)
        pressed.add(pygame.K_DOWN)

    if decision.move_x < -0.22:
        pressed.add(pygame.K_a)
        pressed.add(pygame.K_LEFT)
    elif decision.move_x > 0.22:
        pressed.add(pygame.K_d)
        pressed.add(pygame.K_RIGHT)

    if decision.melee:
        pressed.add(pygame.K_z)

    if decision.defend:
        pressed.add(pygame.K_SPACE)

    return VirtualKeys(pressed)


class AutoPlayerAgent:
    """Heuristic policy controlled by genetic weights."""

    def __init__(
        self,
        weights: dict[str, float],
        seed: int = 7,
        path_hint: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None = None,
    ):
        self.weights = dict(weights)
        self.rng = random.Random(seed)
        self._shoot_cooldown = 0
        self._last_player_pos: pygame.Vector2 | None = None
        self._last_move_command = pygame.Vector2(0.0, 0.0)
        self._stuck_frames = 0
        self._unstuck_timer = 0
        self._unstuck_direction = pygame.Vector2(0.0, 0.0)
        self._unstuck_index = 0
        self._stalking_timer = 0
        self._stalking_direction = pygame.Vector2(0.0, 0.0)
        self._stalking_side = 1
        self._last_target_distance: float | None = None
        self._oscillation_score = 0.0
        self._probe_masks: dict[tuple[int, int], pygame.mask.Mask] = {}
        self._path_hint = [pygame.Vector2(float(x), float(y)) for x, y in (path_hint or ())]
        self._path_hint_index = 0
        self._decision_frames = 0

    @classmethod
    def from_genome(
        cls,
        genome: Genome | None,
        seed: int = 7,
        path_hint: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None = None,
    ) -> "AutoPlayerAgent":
        if genome is None:
            genome = default_genome()
        return cls(weights=dict(genome.genes), seed=seed, path_hint=path_hint)

    def _nearest_enemy(self, player_center: pygame.Vector2, enemies) -> tuple[pygame.sprite.Sprite | None, float]:
        nearest = None
        nearest_dist = float("inf")
        for enemy in enemies:
            rect = getattr(enemy, "hitbox", getattr(enemy, "rect", None))
            if rect is None:
                continue
            dist = player_center.distance_to(pygame.Vector2(float(rect.centerx), float(rect.centery)))
            if dist < nearest_dist:
                nearest = enemy
                nearest_dist = dist
        return nearest, nearest_dist

    def _seek_potion(self, player_center: pygame.Vector2, item_manager) -> tuple[float, float, float] | None:
        if item_manager is None:
            return None
        targets = item_manager.get_active_potion_positions(("vida", "escudo"))
        if not targets:
            return None

        target = min(targets, key=lambda item: player_center.distance_to(item[1]))[1]
        vec = target - player_center
        distance = float(vec.length())
        if vec.length_squared() <= 1e-6:
            return 0.0, 0.0, 0.0
        vec = vec.normalize()
        return float(vec.x), float(vec.y), distance

    def _compute_hazard_avoidance(
        self,
        player_center: pygame.Vector2,
        player,
        game_map,
    ) -> tuple[pygame.Vector2, float] | None:
        if game_map is None:
            return None
        hazard_rects = getattr(game_map, "hazard_rects", None)
        if not hazard_rects:
            return None

        max_probe = max(72.0, float(max(player.hitbox.width, player.hitbox.height)) * 4.2)
        safety_expand = max(12, int(max(player.hitbox.width, player.hitbox.height) * 0.70))

        repulse = pygame.Vector2(0.0, 0.0)
        nearest_dist = float("inf")
        for rect in hazard_rects:
            probe = rect.inflate(safety_expand * 2, safety_expand * 2)
            nearest_x = min(max(float(player_center.x), float(probe.left)), float(probe.right))
            nearest_y = min(max(float(player_center.y), float(probe.top)), float(probe.bottom))
            nearest_pt = pygame.Vector2(nearest_x, nearest_y)
            away = player_center - nearest_pt
            distance = float(away.length())
            if distance > max_probe:
                continue

            nearest_dist = min(nearest_dist, distance)
            if away.length_squared() <= 1e-9:
                away = pygame.Vector2(self.rng.uniform(-1.0, 1.0), self.rng.uniform(-1.0, 1.0))
                if away.length_squared() <= 1e-9:
                    away = pygame.Vector2(1.0, 0.0)

            intensity = max(0.0, min(1.0, (max_probe - distance) / max_probe))
            repulse += away.normalize() * (0.45 + (1.75 * intensity))

        if repulse.length_squared() <= 1e-9:
            return None

        urgency = max(0.0, min(1.0, (max_probe - nearest_dist) / max_probe))
        if nearest_dist <= (safety_expand * 0.60):
            urgency = max(urgency, 0.85)
        return repulse.normalize(), urgency

    def _inject_hazard_avoidance(
        self,
        desired_move: pygame.Vector2,
        hazard_dir: pygame.Vector2 | None,
        hazard_urgency: float,
    ) -> pygame.Vector2:
        if hazard_dir is None or hazard_urgency <= 0.0:
            return desired_move

        base_mag = float(desired_move.length())
        if desired_move.length_squared() <= 1e-9:
            mixed = hazard_dir
        else:
            keep = max(0.08, 1.0 - (0.70 * hazard_urgency))
            avoid = min(0.95, 0.22 + (0.95 * hazard_urgency))
            mixed = (desired_move.normalize() * keep) + (hazard_dir * avoid)
        if mixed.length_squared() <= 1e-9:
            mixed = hazard_dir

        out_mag = min(1.0, max(base_mag, 0.42 + (0.42 * hazard_urgency)))
        return mixed.normalize() * out_mag

    def _get_probe_mask(self, width: int, height: int) -> pygame.mask.Mask:
        key = (max(1, int(width)), max(1, int(height)))
        cached = self._probe_masks.get(key)
        if cached is not None:
            return cached
        surf = pygame.Surface(key, pygame.SRCALPHA)
        surf.fill((255, 255, 255, 255))
        mask = pygame.mask.from_surface(surf)
        self._probe_masks[key] = mask
        return mask

    def _rect_hits_collision(self, rect: pygame.Rect, game_map) -> bool:
        if game_map is None:
            return False

        map_w = int(getattr(game_map, "map_width", 0) or 0)
        map_h = int(getattr(game_map, "map_height", 0) or 0)
        if map_w > 0 and map_h > 0:
            if rect.left < 0 or rect.top < 0 or rect.right > map_w or rect.bottom > map_h:
                return True

        collision_mask = getattr(game_map, "collision_mask", None)
        if collision_mask is not None:
            probe_mask = self._get_probe_mask(rect.width, rect.height)
            if collision_mask.overlap(probe_mask, (rect.x, rect.y)) is not None:
                return True
        else:
            for blocked in getattr(game_map, "collision_rects", []):
                if rect.colliderect(blocked):
                    return True

        if hasattr(game_map, "get_dynamic_collisions"):
            for blocked in game_map.get_dynamic_collisions() or []:
                if rect.colliderect(blocked):
                    return True

        if hasattr(game_map, "is_inside_play_area"):
            cx, cy = rect.center
            if not game_map.is_inside_play_area(float(cx), float(cy), margin=0):
                return True

        return False

    def _can_move(self, player, game_map, move_vec: pygame.Vector2, step_px: float) -> bool:
        if game_map is None or move_vec.length_squared() <= 1e-6:
            return True
        probe = getattr(player, "hitbox", player.rect).copy()
        delta = move_vec.normalize() * max(2.0, float(step_px))
        probe.centerx += int(round(delta.x))
        probe.centery += int(round(delta.y))
        return not self._rect_hits_collision(probe, game_map)

    def _update_oscillation(self, move_vec: pygame.Vector2):
        if move_vec.length_squared() <= 1e-6:
            self._oscillation_score = max(0.0, self._oscillation_score - 0.25)
            return
        if self._last_move_command.length_squared() > 1e-6:
            prev = self._last_move_command.normalize()
            cur = move_vec.normalize()
            turn = float(prev.dot(cur))
            if turn < -0.55:
                self._oscillation_score = min(100.0, self._oscillation_score + 2.5)
            else:
                self._oscillation_score = max(0.0, self._oscillation_score - 0.35)
        self._last_move_command = move_vec.normalize()

    def _pick_stalking_detour(
        self,
        target_dir: pygame.Vector2,
        player,
        game_map,
        step_px: float,
        side_hint: int | None = None,
    ) -> tuple[pygame.Vector2, int] | None:
        if target_dir.length_squared() <= 1e-6:
            return None
        base = target_dir.normalize()
        preferred_side = int(side_hint if side_hint is not None else self._stalking_side)
        side_order = [preferred_side, -preferred_side]

        for side in side_order:
            perp = pygame.Vector2(-base.y, base.x) * float(side)
            candidates = [
                perp,
                perp.rotate(18.0 * side),
                perp.rotate(-18.0 * side),
                (perp * 0.80) + (base * 0.20),
                (perp * 0.65) + (base * 0.35),
                perp.rotate(36.0 * side),
                perp.rotate(-36.0 * side),
            ]
            for cand in candidates:
                if cand.length_squared() <= 1e-6:
                    continue
                cdir = cand.normalize()
                if self._can_move(player, game_map, cdir, step_px=step_px):
                    return cdir, int(side)
        return None

    def _pick_navigable_move(
        self,
        desired_move: pygame.Vector2,
        player,
        game_map,
        goal_direction: pygame.Vector2,
        pathing_weight: float,
    ) -> pygame.Vector2:
        if desired_move.length_squared() <= 1e-6:
            return desired_move
        if game_map is None:
            return desired_move

        move_mag = max(0.35, float(desired_move.length()))
        step_px = max(6.0, float(getattr(player, "speed", 2.0)) * (3.6 + (0.35 * max(0.0, pathing_weight))))
        desired_norm = desired_move.normalize()
        goal_norm = goal_direction.normalize() if goal_direction.length_squared() > 1e-6 else desired_norm
        continuity_dir = self._last_move_command.normalize() if self._last_move_command.length_squared() > 1e-6 else None

        candidates = [
            desired_norm,
            self._stalking_direction.normalize() if self._stalking_direction.length_squared() > 1e-6 else pygame.Vector2(0.0, 0.0),
            continuity_dir if continuity_dir is not None else pygame.Vector2(0.0, 0.0),
            desired_norm.rotate(22),
            desired_norm.rotate(-22),
            desired_norm.rotate(42),
            desired_norm.rotate(-42),
            pygame.Vector2(-desired_norm.y, desired_norm.x),
            pygame.Vector2(desired_norm.y, -desired_norm.x),
            -desired_norm,
        ]

        best_vec = desired_norm
        best_score = -1e9
        found_candidate = False
        for cand in candidates:
            if cand.length_squared() <= 1e-6:
                continue
            if not self._can_move(player, game_map, cand, step_px):
                continue
            found_candidate = True
            align = float(cand.normalize().dot(goal_norm))
            continuity = 0.0
            if continuity_dir is not None:
                continuity = float(cand.normalize().dot(continuity_dir))
            score = align + (0.15 * max(0.0, pathing_weight)) + (0.22 * continuity)
            if self._stuck_frames > 10 and continuity < -0.45:
                score -= 0.60
            if score > best_score:
                best_score = score
                best_vec = cand.normalize()
        if found_candidate:
            return best_vec * move_mag

        # Fallback duro: buscar cualquier direccion navegable en abanico amplio.
        sweep_step = 22
        for angle in range(0, 360, sweep_step):
            cand = desired_norm.rotate(float(angle))
            if self._can_move(player, game_map, cand, step_px=max(4.0, step_px * 0.75)):
                return cand.normalize() * move_mag

        # Sin salida: detenerse para que entre en modo unstuck, en lugar de empujar pared.
        return pygame.Vector2(0.0, 0.0)

    def _build_unstuck_direction(self, to_target: pygame.Vector2, player, game_map) -> pygame.Vector2:
        if to_target.length_squared() > 1e-6:
            base = to_target.normalize()
        else:
            base = pygame.Vector2(1.0, 0.0)

        directions = [
            base,
            base.rotate(35),
            base.rotate(-35),
            base.rotate(70),
            base.rotate(-70),
            pygame.Vector2(-base.y, base.x),
            pygame.Vector2(base.y, -base.x),
            -base,
        ]

        for offset in range(len(directions)):
            idx = (self._unstuck_index + offset) % len(directions)
            candidate = directions[idx]
            if self._can_move(player, game_map, candidate, step_px=max(8.0, float(getattr(player, "speed", 2.0)) * 4.0)):
                self._unstuck_index = idx + 1
                return candidate.normalize()

        self._unstuck_index += 1
        return base

    def _path_hint_direction(self, player_center: pygame.Vector2) -> pygame.Vector2 | None:
        if not self._path_hint:
            return None
        while self._path_hint_index < len(self._path_hint):
            waypoint = self._path_hint[self._path_hint_index]
            vec = waypoint - player_center
            reach_radius = 22.0 if self._stuck_frames < 22 else 34.0
            if vec.length() <= reach_radius:
                self._path_hint_index += 1
                continue
            if vec.length_squared() <= 1e-6:
                return None
            return vec.normalize()
        return None

    def set_path_hint(
        self,
        path_hint: list[tuple[int, int]] | tuple[tuple[int, int], ...] | None,
        player_center: tuple[int, int] | None = None,
    ):
        self._path_hint = [pygame.Vector2(float(x), float(y)) for x, y in (path_hint or ())]
        self._path_hint_index = 0
        if not self._path_hint or player_center is None:
            return
        probe = pygame.Vector2(float(player_center[0]), float(player_center[1]))
        nearest_idx = 0
        nearest_dist = float("inf")
        for idx, waypoint in enumerate(self._path_hint):
            dist = probe.distance_to(waypoint)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_idx = idx
        self._path_hint_index = nearest_idx

    def decide(
        self,
        player,
        enemies,
        objective_complete: bool,
        exit_rect: pygame.Rect | None,
        item_manager,
        game_map=None,
    ) -> AgentDecision:
        decision = AgentDecision()
        self._decision_frames += 1
        if self._shoot_cooldown > 0:
            self._shoot_cooldown -= 1

        player_center = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
        if self._last_player_pos is None:
            self._last_player_pos = player_center.copy()
        moved = player_center.distance_to(self._last_player_pos)
        self._last_player_pos = player_center.copy()
        if moved < 0.45:
            self._stuck_frames += 1
        else:
            self._stuck_frames = 0

        aggression = float(self.weights.get("aggression", 1.0))
        survival = float(self.weights.get("survival", 1.0))
        objective = float(self.weights.get("objective", 1.0))
        spacing = float(self.weights.get("spacing", 1.0))
        aim = float(self.weights.get("aim", 1.0))
        stalking = float(self.weights.get("stalking", self.weights.get("pathing", 1.0)))
        unstuck = float(self.weights.get("unstuck", 1.0))

        hp_ratio = float(player.health) / max(1.0, float(player.max_health))
        energy_ratio = float(player.energy) / max(1.0, float(getattr(player, "max_energy", 1.0)))
        low_energy = energy_ratio <= 0.35
        hint_dir = self._path_hint_direction(player_center)
        if hint_dir is not None and self._stuck_frames > 28 and self._path_hint_index < len(self._path_hint):
            # Si el waypoint actual quedo bloqueado, avanzamos al siguiente para evitar ciclos.
            self._path_hint_index = min(len(self._path_hint), self._path_hint_index + 1)
            hint_dir = self._path_hint_direction(player_center)
        hazard_dir: pygame.Vector2 | None = None
        hazard_urgency = 0.0
        hazard_signal = self._compute_hazard_avoidance(player_center, player, game_map)
        if hazard_signal is not None:
            hazard_dir, hazard_urgency = hazard_signal

        if objective_complete:
            if exit_rect is not None:
                target = pygame.Vector2(float(exit_rect.centerx), float(exit_rect.centery))
                vec = target - player_center
                if vec.length_squared() > 1e-6:
                    vec = vec.normalize()
                    step = min(1.0, 0.55 + (objective * 0.25))
                    desired_move = self._inject_hazard_avoidance(vec * step, hazard_dir, hazard_urgency)
                    goal_dir = desired_move.normalize() if desired_move.length_squared() > 1e-6 else vec
                    move = self._pick_navigable_move(
                        desired_move=desired_move,
                        player=player,
                        game_map=game_map,
                        goal_direction=goal_dir,
                        pathing_weight=stalking,
                    )
                    decision.move_x = float(move.x)
                    decision.move_y = float(move.y)
            self._update_oscillation(pygame.Vector2(decision.move_x, decision.move_y))
            self._last_target_distance = None
            self._stalking_timer = 0
            return decision

        if hp_ratio < (0.56 + (0.08 * max(0.0, survival))):
            potion_move = self._seek_potion(player_center, item_manager)
            if potion_move is not None:
                mx, my, potion_distance = potion_move
                potion_dir = pygame.Vector2(float(mx), float(my))
                if hp_ratio < 0.52 or potion_distance <= 220.0:
                    desired_potion = self._inject_hazard_avoidance(
                        potion_dir * min(1.0, 0.64 + (stalking * 0.18)),
                        hazard_dir,
                        hazard_urgency,
                    )
                    goal_dir = desired_potion.normalize() if desired_potion.length_squared() > 1e-6 else potion_dir
                    move = self._pick_navigable_move(
                        desired_move=desired_potion,
                        player=player,
                        game_map=game_map,
                        goal_direction=goal_dir,
                        pathing_weight=stalking,
                    )
                    decision.move_x = float(move.x)
                    decision.move_y = float(move.y)
                if hp_ratio < 0.35:
                    decision.defend = True
                if hp_ratio < 0.52 or potion_distance <= 220.0:
                    self._update_oscillation(pygame.Vector2(decision.move_x, decision.move_y))
                    self._last_target_distance = None
                    return decision

        enemy, enemy_dist = self._nearest_enemy(player_center, enemies)
        if enemy is None:
            if hint_dir is not None:
                desired_follow = self._inject_hazard_avoidance(
                    hint_dir * min(1.0, 0.58 + (stalking * 0.20)),
                    hazard_dir,
                    hazard_urgency,
                )
                follow_goal = desired_follow.normalize() if desired_follow.length_squared() > 1e-6 else hint_dir
                follow = self._pick_navigable_move(
                    desired_move=desired_follow,
                    player=player,
                    game_map=game_map,
                    goal_direction=follow_goal,
                    pathing_weight=stalking,
                )
                decision.move_x = float(follow.x)
                decision.move_y = float(follow.y)
            elif hazard_dir is not None and hazard_urgency > 0.12:
                escape = self._pick_navigable_move(
                    desired_move=hazard_dir * min(1.0, 0.46 + (hazard_urgency * 0.42)),
                    player=player,
                    game_map=game_map,
                    goal_direction=hazard_dir,
                    pathing_weight=stalking,
                )
                decision.move_x = float(escape.x)
                decision.move_y = float(escape.y)
            self._update_oscillation(pygame.Vector2(decision.move_x, decision.move_y))
            self._last_target_distance = None
            self._stalking_timer = 0
            return decision

        stuck_limit = max(14, int(42 - (max(0.0, unstuck) * 9.0)))
        if self._unstuck_timer <= 0 and self._stuck_frames > stuck_limit:
            self._unstuck_timer = max(16, int(18 + (max(0.0, unstuck) * 9.0)))
            enemy_rect_for_unstuck = getattr(enemy, "hitbox", enemy.rect)
            to_enemy = pygame.Vector2(float(enemy_rect_for_unstuck.centerx), float(enemy_rect_for_unstuck.centery)) - player_center
            self._unstuck_direction = self._build_unstuck_direction(to_enemy, player, game_map)

        if self._unstuck_timer > 0:
            self._unstuck_timer -= 1
            if not self._can_move(player, game_map, self._unstuck_direction, step_px=max(7.0, float(getattr(player, "speed", 2.0)) * 4.2)):
                enemy_rect_for_unstuck = getattr(enemy, "hitbox", enemy.rect)
                to_enemy = pygame.Vector2(float(enemy_rect_for_unstuck.centerx), float(enemy_rect_for_unstuck.centery)) - player_center
                self._unstuck_direction = self._build_unstuck_direction(to_enemy, player, game_map)
            unstuck_move = self._inject_hazard_avoidance(self._unstuck_direction, hazard_dir, hazard_urgency)
            decision.move_x = float(unstuck_move.x)
            decision.move_y = float(unstuck_move.y)
            if enemy_dist <= 58.0 and hp_ratio > 0.32:
                decision.melee = True
            self._update_oscillation(pygame.Vector2(decision.move_x, decision.move_y))
            self._last_target_distance = float(enemy_dist)
            return decision

        enemy_rect = getattr(enemy, "hitbox", enemy.rect)
        target = pygame.Vector2(float(enemy_rect.centerx), float(enemy_rect.centery))
        vec = target - player_center
        if vec.length_squared() <= 1e-6:
            vec = pygame.Vector2(0.0, 1.0)
        distance = max(1e-6, vec.length())
        direction = vec.normalize()

        # En contacto/superposicion: priorizar melee siempre.
        overlap_melee_threshold = max(20.0, float(min(player.hitbox.width, player.hitbox.height)) * 0.85)
        if distance <= overlap_melee_threshold:
            decision.melee = True
            engage_push = direction * 0.55
            engage_push = self._inject_hazard_avoidance(engage_push, hazard_dir, hazard_urgency)
            decision.move_x = float(engage_push.x)
            decision.move_y = float(engage_push.y)
            self._update_oscillation(pygame.Vector2(decision.move_x, decision.move_y))
            self._last_target_distance = float(distance)
            return decision
        if hint_dir is not None:
            hint_weight = 0.26 + (0.12 * max(0.0, stalking))
            if distance > 84.0:
                hint_weight += 0.10
            if self._stuck_frames > 16:
                hint_weight += 0.24
            hint_weight = max(0.0, min(0.88, hint_weight))
            blend = (direction * max(0.0, 1.0 - hint_weight)) + (hint_dir * hint_weight)
            if blend.length_squared() > 1e-6:
                direction = blend.normalize()

        min_distance = 52.0 + (10.0 * max(0.0, 1.0 - aggression))
        preferred_distance = 86.0 + (16.0 * max(0.0, spacing))
        if low_energy:
            # Con poca energia conviene buscar corto alcance (melee).
            min_distance = max(30.0, min_distance - 18.0)
            preferred_distance = max(44.0, preferred_distance - 34.0)

        step_probe = max(6.0, float(getattr(player, "speed", 2.0)) * (3.6 + (0.35 * max(0.0, stalking))))
        direct_blocked = not self._can_move(player, game_map, direction, step_px=step_probe)
        prev_target_dist = self._last_target_distance if self._last_target_distance is not None else distance
        progress_delta = float(prev_target_dist - distance)
        forced_move: pygame.Vector2 | None = None

        if self._stalking_timer > 0:
            self._stalking_timer -= 1
            if self._stalking_direction.length_squared() <= 1e-6:
                picked = self._pick_stalking_detour(direction, player, game_map, step_probe, side_hint=self._stalking_side)
                if picked is not None:
                    self._stalking_direction, self._stalking_side = picked
            if self._stalking_direction.length_squared() > 1e-6 and not self._can_move(player, game_map, self._stalking_direction, step_px=step_probe):
                picked = self._pick_stalking_detour(direction, player, game_map, step_probe, side_hint=self._stalking_side)
                if picked is not None:
                    self._stalking_direction, self._stalking_side = picked
            if self._stalking_direction.length_squared() > 1e-6:
                forced_move = self._stalking_direction.normalize() * min(1.0, 0.62 + (objective * 0.22))
            if (not direct_blocked) and progress_delta > 2.0 and self._stuck_frames < 8:
                self._stalking_timer = 0

        if forced_move is None and direct_blocked and distance > 44.0:
            picked = self._pick_stalking_detour(direction, player, game_map, step_probe, side_hint=self._stalking_side)
            if picked is not None:
                self._stalking_direction, self._stalking_side = picked
                commit = max(10, int(14 + (max(0.0, stalking) * 10.0) + min(10.0, self._oscillation_score * 0.25)))
                self._stalking_timer = commit
                forced_move = self._stalking_direction.normalize() * min(1.0, 0.60 + (objective * 0.20))

        if forced_move is not None:
            move = forced_move
        elif distance > preferred_distance:
            speed = min(1.0, 0.56 + (objective * 0.22))
            move = direction * speed
        elif distance < min_distance and hp_ratio < 0.55:
            speed = min(1.0, 0.62 + (survival * 0.22))
            move = (-direction) * speed
        else:
            # Strafe to avoid becoming static while aiming.
            strafe_sign = 1.0 if self.rng.random() > 0.5 else -1.0
            tangent = pygame.Vector2(-direction.y, direction.x) * strafe_sign
            move = tangent * min(0.9, 0.36 + (spacing * 0.28))

        move = self._inject_hazard_avoidance(move, hazard_dir, hazard_urgency)
        goal_direction = move.normalize() if move.length_squared() > 1e-6 else direction
        move = self._pick_navigable_move(
            desired_move=move,
            player=player,
            game_map=game_map,
            goal_direction=goal_direction,
            pathing_weight=stalking,
        )

        decision.move_x = float(move.x)
        decision.move_y = float(move.y)

        melee_threshold = 58.0 if not low_energy else 76.0
        if distance <= melee_threshold and aggression > 0.25 and hp_ratio > 0.30:
            decision.melee = True
            if distance > 26.0:
                engage_push = direction * min(1.0, 0.62 + (aggression * 0.25))
                engage_push = self._inject_hazard_avoidance(engage_push, hazard_dir, hazard_urgency)
                decision.move_x = float(engage_push.x)
                decision.move_y = float(engage_push.y)

        can_shoot = (
            distance >= 76.0
            and distance <= 260.0
            and not decision.melee
            and not low_energy
            and player.energy >= max(1.0, float(getattr(player, "ranged_mana_cost", 1.0)))
        )
        if can_shoot and aim > 0.20 and self._shoot_cooldown <= 0:
            jitter = max(0.0, 1.1 - min(1.0, aim)) * 12.0
            tx = float(target.x + self.rng.uniform(-jitter, jitter))
            ty = float(target.y + self.rng.uniform(-jitter, jitter))
            decision.ranged_target = (tx, ty)
            self._shoot_cooldown = max(8, int(16 - (max(0.0, aim) * 4.0)))

        if hp_ratio < 0.45 and enemy_dist < 92.0 and survival > 0.3:
            decision.defend = True

        self._update_oscillation(pygame.Vector2(decision.move_x, decision.move_y))
        self._last_target_distance = float(distance)
        return decision
