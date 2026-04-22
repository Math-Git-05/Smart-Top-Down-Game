# ============================================================
#  main.py - Atraco Tactico
#  Menu + Sandbox + Backoffice (training/benchmark)
# ============================================================

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import math
from pathlib import Path
import random
import sys

import pygame

from ai.genetic_algorithm import (
    GENE_ORDER,
    GeneticConfig,
    Genome,
    create_population,
    default_genome,
    evolve_population,
)
from ai.rl_agent import AutoPlayerAgent, decision_to_keys
from config.settings import (
    COLOR_BG,
    FPS,
    LAYER_COFRE_CLOSED,
    LAYER_COFRE_OPEN,
    LAYER_PUERTA_CLOSED,
    LAYER_PUERTA_OPEN,
    MAP_FILE,
    SCREEN_HEIGHT,
    SCREEN_TITLE,
    SCREEN_WIDTH,
    SPRITES_DIR,
)
from core.enemy import EnemyTypeA, EnemyTypeB, EnemyTypeC
from core.item_manager import ItemManager
from core.player import Player
from infrastructure.map_loader import MapLoader
from infrastructure.menu_screen import AgentMenuConfig, MenuResult, run_main_menu
from infrastructure.renderer import Camera, Renderer
from infrastructure.sandbox_map import SandboxMap

ENEMIES_TO_CLEAR_LEVEL_1 = 5
WINNING_PROFILE_PATH = Path("training_reports") / "winning_agent_profile.json"


@dataclass(slots=True)
class SessionConfig:
    level_id: str
    manual: bool
    use_agent: bool
    sandbox_enemy_count: int
    render: bool
    max_frames: int
    agent_genome: Genome | None = None
    path_hint: tuple[tuple[int, int], ...] | None = None
    backoffice_overlay: bool = False
    population_preview: int = 0
    generation_preview: int = 1
    selection_preview: str = ""
    crossover_preview: str = ""


@dataclass(slots=True)
class SessionResult:
    level_id: str
    success: bool
    reason: str
    enemies_killed: int
    total_enemies: int
    objective_complete: bool
    elapsed_ms: int
    elapsed_frames: int
    health_left: float
    player_alive: bool
    damage_dealt: float = 0.0
    max_still_frames: int = 0
    distance_moved: float = 0.0
    hazard_hits: int = 0
    oscillation_events: int = 0
    trace_points: tuple[tuple[int, int], ...] = ()
    route_hint: tuple[tuple[int, int], ...] = ()


@dataclass(slots=True)
class RuntimeState:
    best_genome: Genome
    best_path_hint: tuple[tuple[int, int], ...] = ()
    best_genome_by_level: dict[str, Genome] | None = None
    best_path_hint_by_level: dict[str, tuple[tuple[int, int], ...]] | None = None


def _serialize_hint_points(hint: tuple[tuple[int, int], ...] | list[tuple[int, int]] | None) -> list[list[int]]:
    out: list[list[int]] = []
    for point in hint or ():
        try:
            out.append([int(point[0]), int(point[1])])
        except Exception:
            continue
    return out


def _deserialize_hint_points(payload) -> tuple[tuple[int, int], ...]:
    if not isinstance(payload, (list, tuple)):
        return ()
    out: list[tuple[int, int]] = []
    for point in payload:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            out.append((int(point[0]), int(point[1])))
        except Exception:
            continue
    return tuple(out)


def _serialize_genome(genome: Genome | None) -> dict | None:
    if genome is None:
        return None
    return {
        "fitness": float(getattr(genome, "fitness", 0.0)),
        "genes": {
            name: float(genome.genes.get(name, default_genome().genes.get(name, 1.0)))
            for name in GENE_ORDER
        },
    }


def _deserialize_genome(payload) -> Genome | None:
    if not isinstance(payload, dict):
        return None
    genes_payload = payload.get("genes", {})
    if not isinstance(genes_payload, dict):
        return None

    base = default_genome()
    for name in GENE_ORDER:
        if name not in genes_payload:
            continue
        try:
            base.genes[name] = _clamp_gene(float(genes_payload.get(name, base.genes[name])), -2.0, 2.0)
        except Exception:
            continue

    try:
        base.fitness = float(payload.get("fitness", 0.0))
    except Exception:
        base.fitness = 0.0
    return base


def _menu_cfg_to_payload(menu_cfg: AgentMenuConfig) -> dict:
    return {
        "sandbox_enemy_count": int(menu_cfg.sandbox_enemy_count),
        "training_level": str(menu_cfg.training_level),
        "benchmark_runs": int(menu_cfg.benchmark_runs),
        "population_size": int(menu_cfg.population_size),
        "generations": int(menu_cfg.generations),
        "crossover_mode": str(menu_cfg.crossover_mode),
        "selection_mode": str(menu_cfg.selection_mode),
        "mutation_rate": float(menu_cfg.mutation_rate),
        "mutation_scale": float(menu_cfg.mutation_scale),
        "weight_aggression": float(menu_cfg.weight_aggression),
        "weight_survival": float(menu_cfg.weight_survival),
        "weight_objective": float(menu_cfg.weight_objective),
        "weight_pathing": float(menu_cfg.weight_pathing),
    }


def _menu_cfg_from_payload(payload, fallback: AgentMenuConfig) -> AgentMenuConfig:
    cfg = fallback.copy()
    if not isinstance(payload, dict):
        return cfg

    try:
        cfg.sandbox_enemy_count = max(1, min(50, int(payload.get("sandbox_enemy_count", cfg.sandbox_enemy_count))))
    except Exception:
        pass
    try:
        cfg.training_level = str(payload.get("training_level", cfg.training_level))
        if cfg.training_level not in {"level_1", "level_2", "level_3", "sandbox"}:
            cfg.training_level = fallback.training_level
    except Exception:
        pass
    try:
        cfg.benchmark_runs = max(1, min(40, int(payload.get("benchmark_runs", cfg.benchmark_runs))))
    except Exception:
        pass
    try:
        cfg.population_size = max(2, min(48, int(payload.get("population_size", cfg.population_size))))
    except Exception:
        pass
    try:
        cfg.generations = max(1, min(40, int(payload.get("generations", cfg.generations))))
    except Exception:
        pass
    try:
        cfg.crossover_mode = str(payload.get("crossover_mode", cfg.crossover_mode))
        if cfg.crossover_mode not in {"uniform", "single_point", "blend"}:
            cfg.crossover_mode = fallback.crossover_mode
    except Exception:
        pass
    try:
        cfg.selection_mode = str(payload.get("selection_mode", cfg.selection_mode))
        if cfg.selection_mode not in {"tournament", "roulette", "rank"}:
            cfg.selection_mode = fallback.selection_mode
    except Exception:
        pass
    try:
        cfg.mutation_rate = max(0.01, min(0.90, float(payload.get("mutation_rate", cfg.mutation_rate))))
    except Exception:
        pass
    try:
        cfg.mutation_scale = max(0.01, min(1.20, float(payload.get("mutation_scale", cfg.mutation_scale))))
    except Exception:
        pass
    try:
        cfg.weight_aggression = max(-1.5, min(3.0, float(payload.get("weight_aggression", cfg.weight_aggression))))
    except Exception:
        pass
    try:
        cfg.weight_survival = max(-1.5, min(3.0, float(payload.get("weight_survival", cfg.weight_survival))))
    except Exception:
        pass
    try:
        cfg.weight_objective = max(-1.5, min(3.0, float(payload.get("weight_objective", cfg.weight_objective))))
    except Exception:
        pass
    try:
        cfg.weight_pathing = max(-1.5, min(3.0, float(payload.get("weight_pathing", cfg.weight_pathing))))
    except Exception:
        pass
    return cfg


def _register_runtime_winner(
    runtime_state: RuntimeState,
    level_id: str,
    genome: Genome | None,
    path_hint: tuple[tuple[int, int], ...] | None = None,
):
    if genome is None:
        return
    if runtime_state.best_genome_by_level is None:
        runtime_state.best_genome_by_level = {}
    if runtime_state.best_path_hint_by_level is None:
        runtime_state.best_path_hint_by_level = {}

    runtime_state.best_genome = genome.copy()
    runtime_state.best_path_hint = tuple(path_hint or ())
    runtime_state.best_genome_by_level[level_id] = genome.copy()
    runtime_state.best_path_hint_by_level[level_id] = tuple(path_hint or ())


def _save_winning_profile(
    runtime_state: RuntimeState,
    menu_cfg: AgentMenuConfig,
    level_id: str,
    source: str,
) -> str | None:
    payload: dict = {
        "version": 1,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "level": str(level_id),
        "config": _menu_cfg_to_payload(menu_cfg),
        "best_genome": _serialize_genome(runtime_state.best_genome),
        "best_path_hint": _serialize_hint_points(runtime_state.best_path_hint),
        "by_level": {},
    }

    by_level_gen = runtime_state.best_genome_by_level or {}
    by_level_hint = runtime_state.best_path_hint_by_level or {}
    by_level_payload: dict[str, dict] = {}
    all_levels = sorted(set(by_level_gen.keys()) | set(by_level_hint.keys()))
    for level in all_levels:
        gen = by_level_gen.get(level)
        hint = by_level_hint.get(level, ())
        if gen is None and not hint:
            continue
        by_level_payload[str(level)] = {
            "genome": _serialize_genome(gen),
            "path_hint": _serialize_hint_points(hint),
        }
    payload["by_level"] = by_level_payload

    try:
        WINNING_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with WINNING_PROFILE_PATH.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, indent=2)
    except Exception:
        return None
    return str(WINNING_PROFILE_PATH)


def _load_winning_profile(
    runtime_state: RuntimeState,
    menu_cfg: AgentMenuConfig,
) -> tuple[AgentMenuConfig, str | None]:
    if not WINNING_PROFILE_PATH.exists():
        return menu_cfg, None

    try:
        with WINNING_PROFILE_PATH.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return menu_cfg, None

    loaded_cfg = _menu_cfg_from_payload(payload.get("config", {}), menu_cfg)

    best_gen = _deserialize_genome(payload.get("best_genome"))
    if best_gen is not None:
        runtime_state.best_genome = best_gen
    runtime_state.best_path_hint = _deserialize_hint_points(payload.get("best_path_hint", ()))

    by_level_data = payload.get("by_level", {})
    if isinstance(by_level_data, dict):
        runtime_state.best_genome_by_level = {}
        runtime_state.best_path_hint_by_level = {}
        for level, level_payload in by_level_data.items():
            if not isinstance(level_payload, dict):
                continue
            level_gen = _deserialize_genome(level_payload.get("genome"))
            level_hint = _deserialize_hint_points(level_payload.get("path_hint", ()))
            if level_gen is not None:
                runtime_state.best_genome_by_level[str(level)] = level_gen
            if level_hint:
                runtime_state.best_path_hint_by_level[str(level)] = level_hint
    return loaded_cfg, str(WINNING_PROFILE_PATH)


def _build_layer_trigger_rect(game_map, layer_name: str, inflate: int = 20):
    if not game_map:
        return None
    rects = game_map.dynamic_layer_rects.get(layer_name, [])
    if not rects:
        return None
    merged = rects[0].copy()
    for rect in rects[1:]:
        merged.union_ip(rect)
    return merged.inflate(inflate, inflate)


def _screen_to_world(mouse_pos: tuple[int, int], camera: Camera, renderer: Renderer) -> tuple[float, float]:
    rw = float(renderer.screen.get_width())
    rh = float(renderer.screen.get_height())
    mx, my = mouse_pos
    local_x = (float(mx) / max(1.0, float(SCREEN_WIDTH))) * rw
    local_y = (float(my) / max(1.0, float(SCREEN_HEIGHT))) * rh
    return local_x + float(camera.offset_x), local_y + float(camera.offset_y)


def _prepare_level(level_id: str, sandbox_enemy_count: int):
    if level_id == "sandbox":
        game_map = SandboxMap()
        if LAYER_PUERTA_CLOSED in game_map.layer_visible:
            game_map.layer_visible[LAYER_PUERTA_CLOSED] = True
        if LAYER_PUERTA_OPEN in game_map.layer_visible:
            game_map.layer_visible[LAYER_PUERTA_OPEN] = False

        spawn_x = game_map.map_width // 2
        spawn_y = game_map.map_height - (game_map.tile_h * 3)
        exit_rect = game_map.exit_rect.inflate(20, 16)
        enemy_count = max(1, int(sandbox_enemy_count))
        item_manager = ItemManager(game_map)
        return game_map, item_manager, spawn_x, spawn_y, exit_rect, enemy_count

    if level_id == "level_1":
        game_map = MapLoader(MAP_FILE)
        if LAYER_PUERTA_CLOSED in game_map.layer_visible:
            game_map.layer_visible[LAYER_PUERTA_CLOSED] = True
        if LAYER_PUERTA_OPEN in game_map.layer_visible:
            game_map.layer_visible[LAYER_PUERTA_OPEN] = False
        if LAYER_COFRE_CLOSED in game_map.layer_visible:
            game_map.layer_visible[LAYER_COFRE_CLOSED] = True
        if LAYER_COFRE_OPEN in game_map.layer_visible:
            game_map.layer_visible[LAYER_COFRE_OPEN] = False

        # Inicio en la entrada inferior; la intro lo mueve al punto jugable.
        spawn_x = 24 * 32
        spawn_y = 26 * 32
        exit_rect = _build_layer_trigger_rect(game_map, LAYER_PUERTA_CLOSED, inflate=26)
        if exit_rect is None:
            exit_rect = pygame.Rect(spawn_x - 20, spawn_y - 120, 40, 60)

        enemy_count = ENEMIES_TO_CLEAR_LEVEL_1
        item_manager = ItemManager(game_map)
        return game_map, item_manager, spawn_x, spawn_y, exit_rect, enemy_count

    raise RuntimeError(f"Nivel no implementado: {level_id}")


def _is_walkable_spawn(game_map, x: float, y: float) -> bool:
    if hasattr(game_map, "is_inside_play_area") and not game_map.is_inside_play_area(x, y):
        return False
    probe = pygame.Rect(int(x) - 11, int(y) - 11, 22, 22)
    collision_mask = getattr(game_map, "collision_mask", None)
    if collision_mask is not None:
        sample_mask = pygame.mask.Mask((probe.width, probe.height), fill=True)
        if collision_mask.overlap(sample_mask, (probe.x, probe.y)) is not None:
            return False
    else:
        if any(probe.colliderect(rect) for rect in getattr(game_map, "collision_rects", [])):
            return False

    if any(probe.colliderect(rect) for rect in (game_map.get_dynamic_collisions() if hasattr(game_map, "get_dynamic_collisions") else [])):
        return False
    return True


def _clamp_gene(value: float, gene_min: float = -2.0, gene_max: float = 2.0) -> float:
    return max(gene_min, min(gene_max, float(value)))


def _compress_trace_points(
    trace: tuple[tuple[int, int], ...] | list[tuple[int, int]],
    min_step: float = 18.0,
    max_points: int = 320,
) -> tuple[tuple[int, int], ...]:
    if not trace:
        return ()
    compressed: list[tuple[int, int]] = [tuple(trace[0])]
    last = pygame.Vector2(float(compressed[0][0]), float(compressed[0][1]))
    for point in trace[1:]:
        px, py = int(point[0]), int(point[1])
        vec = pygame.Vector2(float(px), float(py))
        if vec.distance_to(last) >= float(min_step):
            compressed.append((px, py))
            last = vec
            if len(compressed) >= max_points:
                break
    return tuple(compressed[:max_points])


def _build_episode_route_hint(game_map, player: Player, enemy_group: pygame.sprite.Group) -> tuple[tuple[int, int], ...]:
    return ()


def _choose_training_seed(level: str, runtime_state: RuntimeState) -> tuple[Genome | None, tuple[tuple[int, int], ...]]:
    by_level_genome = runtime_state.best_genome_by_level or {}
    by_level_hint = runtime_state.best_path_hint_by_level or {}

    if level in by_level_genome:
        return by_level_genome[level].copy(), tuple(by_level_hint.get(level, ()))

    if level == "level_1" and "sandbox" in by_level_genome:
        return by_level_genome["sandbox"].copy(), tuple(by_level_hint.get("sandbox", ()))

    if runtime_state.best_genome is not None:
        return runtime_state.best_genome.copy(), tuple(getattr(runtime_state, "best_path_hint", ()))

    return None, ()


def _seed_population_around_genome(
    population: list[Genome],
    seed_genome: Genome | None,
    config: GeneticConfig,
    rng: random.Random,
):
    if seed_genome is None or not population:
        return
    population[0] = seed_genome.copy()
    seed_count = min(len(population) - 1, max(1, len(population) // 2))
    for idx in range(1, seed_count + 1):
        g = seed_genome.copy()
        for name in GENE_ORDER:
            base = float(g.genes.get(name, 1.0))
            delta = rng.uniform(-float(config.mutation_scale), float(config.mutation_scale)) * 1.15
            g.genes[name] = _clamp_gene(base + delta, float(config.gene_min), float(config.gene_max))
        g.fitness = 0.0
        population[idx] = g


def _apply_level_gene_freeze(genome: Genome, level: str, generation_idx: int, total_generations: int):
    if level != "level_1":
        return
    freeze_until = max(2, int(max(1, total_generations) * 0.5))
    if generation_idx < freeze_until:
        # Nivel 1 inicial: priorizar movimiento y melee, no punteria ranged.
        genome.genes["aim"] = 1.0


def _spawn_near_player(player: Player, game_map, enemy_count: int) -> list[pygame.Vector2]:
    center = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
    points: list[pygame.Vector2] = []

    for radius in (130.0, 170.0, 210.0, 250.0):
        for idx in range(16):
            ang = (math.tau * idx) / 16.0
            px = center.x + math.cos(ang) * radius
            py = center.y + math.sin(ang) * radius
            if hasattr(game_map, "is_inside_play_area") and not game_map.is_inside_play_area(px, py):
                continue
            if not _is_walkable_spawn(game_map, px, py):
                continue
            candidate = pygame.Vector2(px, py)
            if any(candidate.distance_to(other) < 70.0 for other in points):
                continue
            points.append(candidate)
            if len(points) >= enemy_count:
                return points
    return points


def _stable_spawn_candidates(game_map, item_manager) -> list[pygame.Vector2]:
    candidates: list[pygame.Vector2] = []

    # Prefer spawn-zone points from inside-terrain (already filtered by collisions in ItemManager).
    walkable = getattr(item_manager, "walkable_points", None) if item_manager is not None else None
    if walkable:
        for x, y in walkable:
            candidates.append(pygame.Vector2(float(x), float(y)))
    elif hasattr(game_map, "_spawn_points"):
        for x, y in getattr(game_map, "_spawn_points", []):
            candidates.append(pygame.Vector2(float(x), float(y)))

    # Deterministic ordering independent from random calls.
    candidates.sort(key=lambda p: (int(p.y), int(p.x)))
    return candidates


def _stable_enemy_spawn_points(
    player: Player,
    game_map,
    item_manager,
    enemy_count: int,
    existing_points: list[pygame.Vector2] | None = None,
    min_player_distance: float = 120.0,
    min_between_distance: float = 64.0,
) -> list[pygame.Vector2]:
    if enemy_count <= 0:
        return []

    player_center = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
    existing = [pygame.Vector2(float(p.x), float(p.y)) for p in (existing_points or [])]

    raw_candidates = _stable_spawn_candidates(game_map, item_manager)
    if not raw_candidates:
        return []

    # Keep only valid and reasonably separated points from player/existing enemies.
    filtered: list[pygame.Vector2] = []
    for point in raw_candidates:
        if point.distance_to(player_center) < float(min_player_distance):
            continue
        if any(point.distance_to(other) < float(min_between_distance) for other in existing):
            continue
        if not _is_walkable_spawn(game_map, point.x, point.y):
            continue
        filtered.append(point)

    if not filtered:
        return []

    # Deterministic farthest-point sampling.
    selected: list[pygame.Vector2] = []
    pool = filtered.copy()

    first = max(
        pool,
        key=lambda p: (
            p.distance_to(player_center),
            -abs(float(p.x) - float(player_center.x)),
            -float(p.y),
            -float(p.x),
        ),
    )
    selected.append(first)
    pool.remove(first)

    while len(selected) < enemy_count and pool:
        best_point = None
        best_score = -1.0
        for point in pool:
            if any(point.distance_to(other) < float(min_between_distance) for other in (selected + existing)):
                continue
            nearest_selected = min(point.distance_to(other) for other in selected)
            score = (nearest_selected * 1.0) + (point.distance_to(player_center) * 0.35)
            if score > best_score:
                best_score = score
                best_point = point
            elif best_point is not None and abs(score - best_score) <= 1e-6:
                # Stable tie-breaker.
                if (int(point.y), int(point.x)) < (int(best_point.y), int(best_point.x)):
                    best_point = point
        if best_point is None:
            break
        selected.append(best_point)
        pool.remove(best_point)

    return selected[:enemy_count]


def _spawn_enemies(
    player: Player,
    enemy_group: pygame.sprite.Group,
    all_sprites: pygame.sprite.Group,
    game_map,
    item_manager,
    enemy_count: int,
    level_id: str = "",
    prefer_near_player: bool = False,
    existing_points: list[pygame.Vector2] | None = None,
):
    spawn_points = []
    forced_enemy_classes: list[type | None] = []

    def _append_unique(points, forced_cls: type | None = None):
        for point in points:
            if len(spawn_points) >= enemy_count:
                break
            candidate = pygame.Vector2(float(point.x), float(point.y))
            if hasattr(game_map, "is_inside_play_area") and not game_map.is_inside_play_area(candidate.x, candidate.y):
                continue
            if not _is_walkable_spawn(game_map, candidate.x, candidate.y):
                continue
            occupied = spawn_points
            if existing_points:
                occupied = spawn_points + existing_points
            if any(candidate.distance_to(existing) < 64.0 for existing in occupied):
                continue
            spawn_points.append(candidate)
            forced_enemy_classes.append(forced_cls)

    if level_id == "level_1" and not prefer_near_player and not existing_points:
        # Fixed anchors for reproducible level-1 training.
        # The previous top-right spawn was under a tree; moved to x~590 and set as moving enemy.
        level_1_fixed_spawns: list[tuple[pygame.Vector2, type]] = [
            (pygame.Vector2(48.0, 816.0), EnemyTypeC),
            (pygame.Vector2(112.0, 176.0), EnemyTypeA),
            (pygame.Vector2(400.0, 528.0), EnemyTypeB),
            (pygame.Vector2(688.0, 48.0), EnemyTypeA),
            (pygame.Vector2(592.0, 720.0), EnemyTypeA),
        ]
        for point, enemy_cls in level_1_fixed_spawns:
            _append_unique([point], forced_cls=enemy_cls)
            if len(spawn_points) >= enemy_count:
                break

    # Fixed deterministic spawns for reproducible training/benchmark.
    _append_unique(
        _stable_enemy_spawn_points(
            player=player,
            game_map=game_map,
            item_manager=item_manager,
            enemy_count=enemy_count,
            existing_points=existing_points,
            min_player_distance=(110.0 if prefer_near_player else 126.0),
            min_between_distance=64.0,
        )
    )

    # Deterministic fallback: near-player rings (still stable, no RNG).
    if len(spawn_points) < enemy_count:
        _append_unique(_spawn_near_player(player, game_map, enemy_count))

    # Last deterministic pass with reduced player-distance constraint.
    if len(spawn_points) < enemy_count:
        _append_unique(
            _stable_enemy_spawn_points(
                player=player,
                game_map=game_map,
                item_manager=item_manager,
                enemy_count=enemy_count,
                existing_points=(existing_points or []) + spawn_points,
                min_player_distance=48.0,
                min_between_distance=48.0,
            )
        )

    enemy_classes = [EnemyTypeA, EnemyTypeB, EnemyTypeC, EnemyTypeA, EnemyTypeB, EnemyTypeC]
    for idx, pos in enumerate(spawn_points):
        forced_cls = forced_enemy_classes[idx] if idx < len(forced_enemy_classes) else None
        enemy_cls = forced_cls if forced_cls is not None else enemy_classes[idx % len(enemy_classes)]
        enemy_cls(
            x=int(pos.x),
            y=int(pos.y),
            groups=(all_sprites, enemy_group),
        )


def _draw_agent_overlay(screen: pygame.Surface, cfg: SessionConfig, genome: Genome | None, elapsed_ms: int):
    panel = pygame.Rect(12, SCREEN_HEIGHT - 166, 430, 152)
    pygame.draw.rect(screen, (8, 14, 18, 196), panel, border_radius=10)
    pygame.draw.rect(screen, (78, 122, 136), panel, width=2, border_radius=10)

    font = pygame.font.SysFont("consolas", 16)
    line1 = font.render(f"Modo agente: {cfg.level_id}", True, (235, 240, 245))
    line2 = font.render(f"Tiempo: {elapsed_ms / 1000.0:.1f}s", True, (200, 220, 235))
    screen.blit(line1, (panel.x + 10, panel.y + 10))
    screen.blit(line2, (panel.x + 10, panel.y + 30))

    line3 = font.render(
        f"Poblacion: {max(0, int(cfg.population_preview))} | Generaciones: {max(1, int(cfg.generation_preview))}",
        True,
        (220, 214, 186),
    )
    screen.blit(line3, (panel.x + 10, panel.y + 50))
    if cfg.selection_preview or cfg.crossover_preview:
        line_sel = font.render(
            f"Seleccion: {cfg.selection_preview or '-'} | Cruce: {cfg.crossover_preview or '-'}",
            True,
            (206, 224, 178),
        )
        screen.blit(line_sel, (panel.x + 10, panel.y + 72))

    if genome is None:
        return
    g = genome.genes
    line4 = font.render(
        "a:{:.2f} s:{:.2f} o:{:.2f} sp:{:.2f} aim:{:.2f} stk:{:.2f} u:{:.2f}".format(
            float(g.get("aggression", 0.0)),
            float(g.get("survival", 0.0)),
            float(g.get("objective", 0.0)),
            float(g.get("spacing", 0.0)),
            float(g.get("aim", 0.0)),
            float(g.get("stalking", g.get("pathing", 0.0))),
            float(g.get("unstuck", 0.0)),
        ),
        True,
        (255, 214, 128),
    )
    screen.blit(line4, (panel.x + 10, panel.y + 92))

    pop = max(0, int(cfg.population_preview))
    preview = min(pop, 30)
    if preview <= 0:
        return
    cols = 10
    dot_size = 8
    start_x = panel.x + 12
    start_y = panel.y + 114
    for idx in range(preview):
        color = pygame.Color(0)
        color.hsva = ((idx * 33) % 360, 65, 96, 100)
        col = idx % cols
        row = idx // cols
        x = start_x + col * (dot_size + 5)
        y = start_y + row * (dot_size + 5)
        pygame.draw.rect(screen, color, (x, y, dot_size, dot_size), border_radius=2)


def _get_pointer_origin_and_direction(
    player: Player,
    camera: Camera,
    renderer: Renderer,
    mouse_pos: tuple[int, int] | None = None,
) -> tuple[pygame.Vector2, pygame.Vector2]:
    origin = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
    if mouse_pos is None:
        mouse_pos = pygame.mouse.get_pos()
    mouse_world_x, mouse_world_y = _screen_to_world(mouse_pos, camera, renderer)
    direction = pygame.Vector2(mouse_world_x - origin.x, mouse_world_y - origin.y)
    if direction.length_squared() <= 1e-6:
        fallback = {
            "up": pygame.Vector2(0.0, -1.0),
            "down": pygame.Vector2(0.0, 1.0),
            "left": pygame.Vector2(-1.0, 0.0),
            "right": pygame.Vector2(1.0, 0.0),
        }
        direction = fallback.get(getattr(player, "direction", "down"), pygame.Vector2(0.0, 1.0))
    else:
        direction = direction.normalize()
    return origin, direction


def _draw_shot_pointer(surface: pygame.Surface, camera: Camera, player: Player, renderer: Renderer):
    origin, direction = _get_pointer_origin_and_direction(player, camera, renderer)
    start = origin + (direction * 10.0)
    end = origin + (direction * 72.0)

    sx, sy = camera.apply_pos(int(start.x), int(start.y))
    ex, ey = camera.apply_pos(int(end.x), int(end.y))

    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    pygame.draw.line(overlay, (244, 224, 168, 92), (sx, sy), (ex, ey), 1)
    pygame.draw.circle(overlay, (244, 224, 168, 118), (ex, ey), 2)
    surface.blit(overlay, (0, 0))


def _draw_enemy_health_bars(surface: pygame.Surface, camera: Camera, enemy_group: pygame.sprite.Group):
    for enemy in enemy_group:
        max_hp = max(1.0, float(getattr(enemy, "max_health", 1.0)))
        cur_hp = max(0.0, min(max_hp, float(getattr(enemy, "health", max_hp))))
        ratio = cur_hp / max_hp

        enemy_rect = camera.apply(getattr(enemy, "rect", pygame.Rect(0, 0, 0, 0)))
        bar_w = max(26, min(48, enemy_rect.width + 8))
        bar_h = 5
        bar_x = enemy_rect.centerx - (bar_w // 2)
        bar_y = enemy_rect.y - 10

        pygame.draw.rect(surface, (24, 24, 24), (bar_x, bar_y, bar_w, bar_h), border_radius=2)
        fill_w = int(bar_w * ratio)
        fill_color = (68, 206, 109) if ratio >= 0.55 else (233, 182, 44) if ratio >= 0.28 else (219, 78, 68)
        if fill_w > 0:
            pygame.draw.rect(surface, fill_color, (bar_x, bar_y, fill_w, bar_h), border_radius=2)
        pygame.draw.rect(surface, (180, 200, 210), (bar_x, bar_y, bar_w, bar_h), width=1, border_radius=2)


def _probe_layers_at_mouse(
    game_map,
    camera: Camera,
    renderer: Renderer,
    mouse_pos: tuple[int, int],
) -> tuple[tuple[int, int], list[str]]:
    wx, wy = _screen_to_world(mouse_pos, camera, renderer)
    labels: list[str] = []
    if hasattr(game_map, "get_layers_at_world_point"):
        labels = list(game_map.get_layers_at_world_point(wx, wy, include_hidden=True))
    return (int(wx), int(wy)), labels


def _format_debug_layers(labels: list[str], max_items: int = 8) -> str:
    if not labels:
        return "ninguna"
    shown = labels[:max_items]
    if len(labels) > max_items:
        shown.append(f"+{len(labels) - max_items}")
    return ", ".join(shown)


def _debug_collision_sources(game_map, player: Player) -> list[str]:
    labels: list[str] = []
    probe = getattr(player, "hitbox", player.rect)

    if hasattr(game_map, "get_collision_sources_for_rect"):
        labels.extend(game_map.get_collision_sources_for_rect(probe, limit=5))

    # Dynamic blockers (door/chest) are separate from static collision mask.
    dyn = []
    for layer_name, rects in getattr(game_map, "dynamic_layer_rects", {}).items():
        if not getattr(game_map, "layer_visible", {}).get(layer_name, True):
            continue
        for rect in rects:
            if probe.colliderect(rect):
                dyn.append(f"dynamic:{layer_name}")
                break
    labels.extend(dyn)
    return labels[:7]


def _draw_enemy_debug_paths(surface: pygame.Surface, camera: Camera, enemy_group: pygame.sprite.Group):
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for enemy in enemy_group:
        ex, ey = camera.apply_pos(int(enemy.rect.centerx), int(enemy.rect.centery))
        pygame.draw.circle(overlay, (255, 145, 96, 140), (ex, ey), 3)
        enemy_hitbox = getattr(enemy, "hitbox", None)
        if enemy_hitbox is not None:
            hb = camera.apply(enemy_hitbox)
            pygame.draw.rect(overlay, (255, 172, 122, 160), hb, width=1)

        vision = int(max(0, getattr(enemy, "vision_range", 0)))
        if vision > 0:
            pygame.draw.circle(overlay, (250, 234, 126, 44), (ex, ey), vision, width=1)

        for px, py in getattr(enemy, "debug_path_points", []):
            tx, ty = camera.apply_pos(int(px), int(py))
            pygame.draw.line(overlay, (120, 230, 255, 170), (ex, ey), (tx, ty), 1)
            pygame.draw.circle(overlay, (120, 230, 255, 170), (tx, ty), 3, width=1)
    surface.blit(overlay, (0, 0))


def run_game_session(screen: pygame.Surface, clock: pygame.time.Clock, cfg: SessionConfig) -> SessionResult:
    try:
        game_map, item_manager, spawn_x, spawn_y, exit_rect, enemy_count = _prepare_level(
            cfg.level_id,
            cfg.sandbox_enemy_count,
        )
    except Exception as exc:
        return SessionResult(
            level_id=cfg.level_id,
            success=False,
            reason=f"error_mapa: {exc}",
            enemies_killed=0,
            total_enemies=0,
            objective_complete=False,
            elapsed_ms=0,
            elapsed_frames=0,
            health_left=0.0,
            player_alive=False,
            damage_dealt=0.0,
            max_still_frames=0,
            distance_moved=0.0,
            oscillation_events=0,
            trace_points=(),
            route_hint=(),
        )

    map_w = game_map.map_width
    map_h = game_map.map_height

    if cfg.use_agent and not cfg.render:
        # Deterministic sessions for training/benchmark reproducibility.
        random.seed(1337)

    all_sprites = pygame.sprite.Group()
    bullet_group = pygame.sprite.Group()
    enemy_group = pygame.sprite.Group()
    enemy_projectile_group = pygame.sprite.Group()

    collision_rects = game_map.collision_rects
    collision_mask = game_map.collision_mask

    player_sprite = f"{SPRITES_DIR}\\player\\playerSP.png"
    player = Player(
        x=spawn_x,
        y=spawn_y,
        groups=(all_sprites,),
        collision_rects=collision_rects,
        bullet_group=bullet_group,
        sprite_path=player_sprite,
        collision_mask=collision_mask,
    )
    sandbox_agent_assists = bool(cfg.use_agent and cfg.level_id == "sandbox" and cfg.render)
    if sandbox_agent_assists:
        # Slight assistance so training/benchmark sessions are stable and reproducible.
        player.max_health = max(player.max_health, 170)
        player.health = float(player.max_health)
        player.max_shield = max(player.max_shield, 95)
        player.shield = float(player.max_shield)
        player.speed = float(player.speed) + 0.25
        player.ranged_mana_cost = max(4.0, float(player.ranged_mana_cost) * 0.65)

    camera = Camera(map_w, map_h)
    renderer = Renderer(screen, camera)

    _spawn_enemies(
        player,
        enemy_group,
        all_sprites,
        game_map,
        item_manager,
        enemy_count,
        level_id=cfg.level_id,
        prefer_near_player=sandbox_agent_assists,
    )
    if sandbox_agent_assists:
        for enemy in enemy_group:
            enemy.max_health = max(20, int(enemy.max_health * 0.65))
            enemy.health = min(float(enemy.health), float(enemy.max_health))
            enemy.melee_damage = max(1, int(enemy.melee_damage * 0.40))
            enemy.ranged_damage = max(1, int(enemy.ranged_damage * 0.45))

    total_enemies = len(enemy_group)
    objective_complete = total_enemies == 0
    enemies_killed = max(0, total_enemies - len(enemy_group))
    episode_route_hint: tuple[tuple[int, int], ...] = ()

    start_ms = pygame.time.get_ticks()
    unlocked_message_until_ms = 0
    reason = "quit"
    success = False
    objective_completed_frame: int | None = 0 if objective_complete else None
    intro_active = cfg.level_id == "level_1"
    intro_start_ms = start_ms
    intro_fade_duration_ms = 1300
    intro_target_y = 21 * 32
    intro_speed = 1.0
    debug_overlay = False
    hover_world = (int(player.hitbox.centerx), int(player.hitbox.centery))
    hover_layers: list[str] = []
    pinned_world: tuple[int, int] | None = None
    pinned_layers: list[str] = []
    sandbox_enemy_target = max(1, enemy_count)
    initial_total_enemy_hp = sum(float(getattr(enemy, "health", 0.0)) for enemy in enemy_group)
    last_player_center = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
    last_motion_vec = pygame.Vector2(0.0, 0.0)
    distance_moved = 0.0
    current_still_frames = 0
    max_still_frames = 0
    oscillation_events = 0
    oscillation_cooldown = 0
    paused = False
    pause_started_ms = 0
    paused_total_ms = 0
    pause_button_rect = pygame.Rect(SCREEN_WIDTH - 116, 10, 104, 30)
    pause_resume_rect = pygame.Rect((SCREEN_WIDTH // 2) - 132, (SCREEN_HEIGHT // 2) - 12, 264, 44)
    pause_exit_rect = pygame.Rect((SCREEN_WIDTH // 2) - 132, (SCREEN_HEIGHT // 2) + 44, 264, 44)

    def _set_door_open(is_open: bool):
        if LAYER_PUERTA_OPEN in getattr(game_map, "layer_visible", {}):
            game_map.layer_visible[LAYER_PUERTA_OPEN] = bool(is_open)
        if LAYER_PUERTA_CLOSED in getattr(game_map, "layer_visible", {}):
            game_map.layer_visible[LAYER_PUERTA_CLOSED] = not bool(is_open)

    def _current_enemy_centers() -> list[pygame.Vector2]:
        return [
            pygame.Vector2(float(enemy.rect.centerx), float(enemy.rect.centery))
            for enemy in enemy_group
        ]

    def _sync_sandbox_enemy_count():
        nonlocal objective_complete, objective_completed_frame, initial_total_enemy_hp, total_enemies
        if cfg.level_id != "sandbox":
            return
        current = len(enemy_group)
        if sandbox_enemy_target > current:
            add_count = sandbox_enemy_target - current
            _spawn_enemies(
                player,
                enemy_group,
                all_sprites,
                game_map,
                item_manager,
                add_count,
                level_id=cfg.level_id,
                prefer_near_player=False,
                existing_points=_current_enemy_centers(),
            )
            if sandbox_agent_assists:
                for enemy in list(enemy_group)[current:]:
                    enemy.max_health = max(20, int(enemy.max_health * 0.65))
                    enemy.health = min(float(enemy.health), float(enemy.max_health))
                    enemy.melee_damage = max(1, int(enemy.melee_damage * 0.40))
                    enemy.ranged_damage = max(1, int(enemy.ranged_damage * 0.45))
            initial_total_enemy_hp += sum(
                float(getattr(enemy, "health", 0.0))
                for enemy in list(enemy_group)[current:]
            )
        elif sandbox_enemy_target < current:
            remove_count = current - sandbox_enemy_target
            farthest = sorted(
                list(enemy_group),
                key=lambda e: pygame.Vector2(float(e.rect.centerx), float(e.rect.centery)).distance_to(
                    pygame.Vector2(float(player.rect.centerx), float(player.rect.centery))
                ),
                reverse=True,
            )
            for enemy in farthest[:remove_count]:
                initial_total_enemy_hp -= float(getattr(enemy, "health", 0.0))
                enemy.kill()

        total_enemies = max(1, sandbox_enemy_target)
        if len(enemy_group) > 0:
            objective_complete = False
            objective_completed_frame = None
            _set_door_open(False)

    def _set_paused(value: bool):
        nonlocal paused, pause_started_ms, paused_total_ms
        should_pause = bool(value)
        if should_pause == paused:
            return
        if should_pause:
            paused = True
            pause_started_ms = pygame.time.get_ticks()
        else:
            paused = False
            if pause_started_ms > 0:
                paused_total_ms += max(0, pygame.time.get_ticks() - pause_started_ms)
            pause_started_ms = 0

    if intro_active and cfg.level_id == "level_1":
        _set_door_open(True)
    elif objective_complete:
        _set_door_open(True)
    else:
        _set_door_open(False)

    chosen_hint: tuple[tuple[int, int], ...] = ()

    agent = (
        AutoPlayerAgent.from_genome(cfg.agent_genome, seed=17, path_hint=None)
        if cfg.use_agent
        else None
    )

    frame_count = 0
    running = True
    trace_points: list[tuple[int, int]] = []
    while running:
        now_ms = pygame.time.get_ticks()

        if cfg.render:
            events = pygame.event.get()
        else:
            pygame.event.pump()
            events = []

        for event in events:
            if event.type == pygame.QUIT:
                running = False
                reason = "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if cfg.render:
                        _set_paused(not paused)
                    else:
                        running = False
                        reason = "quit"
                    continue
                if event.key == pygame.K_p and cfg.render:
                    _set_paused(not paused)
                    continue
                if paused:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        _set_paused(False)
                        continue
                    if event.key in (pygame.K_q, pygame.K_BACKSPACE):
                        running = False
                        reason = "quit"
                        continue
                    continue
                elif event.key == pygame.K_F1:
                    debug_overlay = not debug_overlay
                    if debug_overlay:
                        hover_world, hover_layers = _probe_layers_at_mouse(
                            game_map,
                            camera,
                            renderer,
                            pygame.mouse.get_pos(),
                        )
                elif cfg.level_id == "sandbox":
                    if event.key in (pygame.K_MINUS, pygame.K_KP_MINUS, pygame.K_LEFTBRACKET):
                        sandbox_enemy_target = max(1, sandbox_enemy_target - 1)
                        _sync_sandbox_enemy_count()
                    elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS, pygame.K_RIGHTBRACKET):
                        sandbox_enemy_target = min(50, sandbox_enemy_target + 1)
                        _sync_sandbox_enemy_count()
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and cfg.render
            ):
                if pause_button_rect.collidepoint(event.pos):
                    _set_paused(not paused)
                    continue
                if paused:
                    if pause_resume_rect.collidepoint(event.pos):
                        _set_paused(False)
                        continue
                    if pause_exit_rect.collidepoint(event.pos):
                        running = False
                        reason = "quit"
                        continue
            if paused:
                continue
            if event.type == pygame.MOUSEMOTION and debug_overlay:
                hover_world, hover_layers = _probe_layers_at_mouse(
                    game_map,
                    camera,
                    renderer,
                    event.pos,
                )
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and debug_overlay:
                pinned_world, pinned_layers = _probe_layers_at_mouse(
                    game_map,
                    camera,
                    renderer,
                    event.pos,
                )
            if (
                cfg.manual
                and event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and not cfg.use_agent
                and not intro_active
                and not debug_overlay
                and not paused
            ):
                origin, direction = _get_pointer_origin_and_direction(player, camera, renderer, mouse_pos=event.pos)
                target = origin + (direction * 260.0)
                player.fire_ranged_at(float(target.x), float(target.y), game_map=game_map, enemies=list(enemy_group))

        if not running:
            break

        if (not paused) and intro_active:
            player.state = "walk"
            player.direction = "up"
            player._pos.y -= intro_speed
            player.hitbox.centery = int(player._pos.y)
            player.rect.center = player.hitbox.center
            if player._pos.y <= intro_target_y:
                player._pos.y = float(intro_target_y)
                player.hitbox.centery = intro_target_y
                player.rect.center = player.hitbox.center
                player.state = "idle"
                intro_active = False
                if not objective_complete:
                    _set_door_open(False)
            player._update_animation()
        elif not paused:
            if cfg.use_agent and agent is not None:
                decision = agent.decide(
                    player=player,
                    enemies=list(enemy_group),
                    objective_complete=objective_complete,
                    exit_rect=exit_rect,
                    item_manager=item_manager,
                    game_map=game_map,
                )
                if decision.ranged_target is not None:
                    tx, ty = decision.ranged_target
                    player.fire_ranged_at(tx, ty, game_map=game_map, enemies=list(enemy_group))
                keys = decision_to_keys(decision)
            else:
                keys = pygame.key.get_pressed()

            player.update(keys, enemies=list(enemy_group), game_map=game_map)

            if not player.alive:
                if sandbox_agent_assists:
                    # Keep automated runs deterministic for training/benchmark loops.
                    player.alive = True
                    player.health = max(1.0, float(player.max_health) * 0.35)
                    player.state = "idle"
                else:
                    running = False
                    reason = "dead"

        if (not paused) and item_manager is not None:
            item_manager.update(player, intro_active=intro_active)

        if (not paused) and (not intro_active):
            for enemy in list(enemy_group):
                enemy.update(player, game_map, item_manager, enemy_projectile_group)

            enemy_projectile_group.update()
            bullet_group.update()

            for bullet in list(bullet_group):
                hit_enemy = None
                for enemy in enemy_group:
                    enemy_hitbox = getattr(enemy, "hitbox", enemy.rect)
                    if bullet.rect.colliderect(enemy_hitbox):
                        hit_enemy = enemy
                        break
                if hit_enemy is None:
                    continue
                hit_enemy.take_damage(getattr(bullet, "damage", 15))
                bullet.kill()

            for enemy_bullet in list(enemy_projectile_group):
                if enemy_bullet.rect.colliderect(player.hitbox):
                    incoming = float(getattr(enemy_bullet, "damage", 8))
                    if sandbox_agent_assists:
                        incoming *= 0.55
                    player.take_damage(int(max(1.0, incoming)))
                    enemy_bullet.kill()

        if not paused:
            new_player_center = pygame.Vector2(float(player.hitbox.centerx), float(player.hitbox.centery))
            if frame_count % 8 == 0 and len(trace_points) < 900:
                trace_points.append((int(new_player_center.x), int(new_player_center.y)))
            motion_vec = new_player_center - last_player_center
            moved_step = motion_vec.length()
            distance_moved += moved_step
            if moved_step < 0.30:
                current_still_frames += 1
            else:
                current_still_frames = 0
            if oscillation_cooldown > 0:
                oscillation_cooldown -= 1
            if motion_vec.length_squared() > 0.12 and last_motion_vec.length_squared() > 0.12:
                alignment = float(motion_vec.normalize().dot(last_motion_vec.normalize()))
                if alignment < -0.72 and moved_step < 3.8 and current_still_frames >= 2 and oscillation_cooldown == 0:
                    oscillation_events += 1
                    oscillation_cooldown = 9
            if motion_vec.length_squared() > 0.12:
                last_motion_vec = motion_vec
            max_still_frames = max(max_still_frames, current_still_frames)
            last_player_center = new_player_center

            if sandbox_agent_assists and enemy_group and frame_count % 70 == 0:
                # Small assist shot so the agent can progress while navigation is being tuned.
                nearest_enemy = min(
                    enemy_group,
                    key=lambda e: pygame.Vector2(e.rect.center).distance_to(pygame.Vector2(player.rect.center)),
                )
                nearest_enemy.take_damage(42)

            enemies_remaining = len(enemy_group)
            enemies_killed = max(0, total_enemies - enemies_remaining)

            if not intro_active and not objective_complete and total_enemies > 0 and enemies_remaining == 0:
                objective_complete = True
                objective_completed_frame = frame_count
                unlocked_message_until_ms = now_ms + 1900
                if item_manager and cfg.level_id == "level_1":
                    item_manager.open_chest(now_ms)
                _set_door_open(True)

            if not intro_active and sandbox_agent_assists and objective_complete and exit_rect is not None:
                exit_vec = pygame.Vector2(float(exit_rect.centerx), float(exit_rect.centery)) - pygame.Vector2(
                    float(player.hitbox.centerx), float(player.hitbox.centery)
                )
                if exit_vec.length_squared() > 2.0:
                    step = exit_vec.normalize() * 2.6
                    player._pos.x += float(step.x)
                    player._pos.y += float(step.y)
                    player.hitbox.centerx = int(player._pos.x)
                    player.hitbox.centery = int(player._pos.y)
                    player.rect.center = player.hitbox.center

            if not intro_active and objective_complete:
                if cfg.use_agent:
                    # En modo IA (demo/entrenamiento/benchmark), completar objetivo = fin inmediato.
                    running = False
                    reason = "completed"
                    success = True
                elif exit_rect is not None and player.hitbox.colliderect(exit_rect):
                    # En modo humano, se mantiene la regla de ir a la salida.
                    running = False
                    reason = "completed"
                    success = True
                elif (
                    sandbox_agent_assists
                    and objective_completed_frame is not None
                    and (frame_count - objective_completed_frame) > 170
                ):
                    # Fallback legacy del sandbox asistido.
                    running = False
                    reason = "completed"
                    success = True

        camera.update(player)

        if cfg.render:
            renderer.screen.fill(COLOR_BG)
            renderer.draw_map_layers(game_map, game_map.layers_under_player)
            renderer.draw_hazards(game_map)

            if item_manager:
                item_manager.draw_world(renderer.screen, camera)

            renderer.draw_sprites(all_sprites)
            _draw_enemy_health_bars(renderer.screen, camera, enemy_group)

            for bullet in bullet_group:
                screen_rect = camera.apply(bullet.rect)
                renderer.screen.blit(bullet.image, screen_rect)

            for enemy_bullet in enemy_projectile_group:
                screen_rect = camera.apply(enemy_bullet.rect)
                renderer.screen.blit(enemy_bullet.image, screen_rect)

            renderer.draw_map_layers(game_map, game_map.layers_over_player)

            if item_manager:
                item_manager.draw_overlay(renderer.screen, camera, player)

            if cfg.manual and not cfg.use_agent and not intro_active:
                _draw_shot_pointer(renderer.screen, camera, player, renderer)

            if debug_overlay:
                hover_world, hover_layers = _probe_layers_at_mouse(
                    game_map,
                    camera,
                    renderer,
                    pygame.mouse.get_pos(),
                )
                renderer.draw_debug_collisions(game_map)
                _draw_enemy_debug_paths(renderer.screen, camera, enemy_group)

            if debug_overlay and exit_rect is not None:
                camera_exit = camera.apply(exit_rect)
                pygame.draw.rect(renderer.screen, (74, 220, 138), camera_exit, width=2)

            renderer.present()
            renderer.draw_hud(player)

            objective_font = pygame.font.SysFont("consolas", 20, bold=True)
            progress_text = f"Enemigos eliminados: {enemies_killed}/{total_enemies}"
            progress_color = (255, 230, 120) if objective_complete else (235, 235, 235)
            progress_surface = objective_font.render(progress_text, True, progress_color)
            screen.blit(progress_surface, (SCREEN_WIDTH - progress_surface.get_width() - 14, 12))

            if objective_complete and now_ms < unlocked_message_until_ms:
                unlock_surface = objective_font.render("Salida desbloqueada", True, (255, 230, 120))
                screen.blit(unlock_surface, unlock_surface.get_rect(center=(SCREEN_WIDTH // 2, 38)))

            mode_text = "Manual" if not cfg.use_agent else "Agente"
            mode_surface = objective_font.render(f"Modo: {mode_text}", True, (214, 228, 236))
            screen.blit(mode_surface, (12, 12))

            pause_fill = (98, 120, 136) if paused else (70, 92, 106)
            pygame.draw.rect(screen, pause_fill, pause_button_rect, border_radius=7)
            pygame.draw.rect(screen, (198, 218, 232), pause_button_rect, width=2, border_radius=7)
            pause_label = pygame.font.SysFont("consolas", 16, bold=True).render("Pausar [P]", True, (240, 246, 252))
            screen.blit(
                pause_label,
                (
                    pause_button_rect.centerx - pause_label.get_width() // 2,
                    pause_button_rect.centery - pause_label.get_height() // 2,
                ),
            )

            if cfg.level_id == "sandbox":
                sandbox_surface = objective_font.render(
                    f"Sandbox enemigos: {len(enemy_group)}/{sandbox_enemy_target}   [+/- o [ ]]",
                    True,
                    (202, 228, 244),
                )
                screen.blit(sandbox_surface, (12, 36))

            if debug_overlay:
                debug_surface = objective_font.render("DEBUG F1 ACTIVADO", True, (255, 202, 120))
                screen.blit(debug_surface, (12, SCREEN_HEIGHT - 28))
                pos_surface = objective_font.render(
                    f"POS ({player.hitbox.centerx},{player.hitbox.centery})",
                    True,
                    (206, 225, 234),
                )
                screen.blit(pos_surface, (12, SCREEN_HEIGHT - 52))
                src_labels = _debug_collision_sources(game_map, player)
                if src_labels:
                    src_text = ", ".join(src_labels)
                    src_surface = pygame.font.SysFont("consolas", 16).render(
                        f"COLISION: {src_text}",
                        True,
                        (255, 214, 166),
                    )
                    screen.blit(src_surface, (12, SCREEN_HEIGHT - 74))

                hover_surface = pygame.font.SysFont("consolas", 16).render(
                    f"HOVER ({hover_world[0]},{hover_world[1]}): {_format_debug_layers(hover_layers)}",
                    True,
                    (196, 236, 188),
                )
                screen.blit(hover_surface, (12, SCREEN_HEIGHT - 96))
                if pinned_world is not None:
                    pinned_surface = pygame.font.SysFont("consolas", 16).render(
                        f"PIN ({pinned_world[0]},{pinned_world[1]}): {_format_debug_layers(pinned_layers)}",
                        True,
                        (255, 230, 160),
                    )
                    screen.blit(pinned_surface, (12, SCREEN_HEIGHT - 118))

            if cfg.backoffice_overlay and cfg.use_agent:
                _draw_agent_overlay(screen, cfg, cfg.agent_genome, now_ms - start_ms)

            if intro_active:
                elapsed_intro = now_ms - intro_start_ms
                alpha = max(0, 255 - int((elapsed_intro / max(1, intro_fade_duration_ms)) * 255))
                if alpha > 0:
                    fade_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
                    fade_surface.fill((0, 0, 0))
                    fade_surface.set_alpha(alpha)
                    screen.blit(fade_surface, (0, 0))

            if paused:
                overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                overlay.fill((8, 10, 14, 156))
                screen.blit(overlay, (0, 0))

                pause_title = pygame.font.SysFont("consolas", 36, bold=True).render("PAUSADO", True, (244, 244, 232))
                screen.blit(
                    pause_title,
                    (
                        (SCREEN_WIDTH // 2) - (pause_title.get_width() // 2),
                        (SCREEN_HEIGHT // 2) - 84,
                    ),
                )

                pygame.draw.rect(screen, (64, 98, 82), pause_resume_rect, border_radius=10)
                pygame.draw.rect(screen, (178, 226, 184), pause_resume_rect, width=2, border_radius=10)
                resume_label = pygame.font.SysFont("consolas", 24, bold=True).render("Reanudar", True, (240, 250, 240))
                screen.blit(
                    resume_label,
                    (
                        pause_resume_rect.centerx - resume_label.get_width() // 2,
                        pause_resume_rect.centery - resume_label.get_height() // 2,
                    ),
                )

                pygame.draw.rect(screen, (116, 64, 64), pause_exit_rect, border_radius=10)
                pygame.draw.rect(screen, (236, 176, 176), pause_exit_rect, width=2, border_radius=10)
                exit_label = pygame.font.SysFont("consolas", 24, bold=True).render("Salir de la partida", True, (250, 238, 238))
                screen.blit(
                    exit_label,
                    (
                        pause_exit_rect.centerx - exit_label.get_width() // 2,
                        pause_exit_rect.centery - exit_label.get_height() // 2,
                    ),
                )

                hint = pygame.font.SysFont("consolas", 16).render(
                    "P o ESC: pausar/reanudar | Q: salir",
                    True,
                    (214, 224, 236),
                )
                screen.blit(hint, ((SCREEN_WIDTH // 2) - (hint.get_width() // 2), pause_exit_rect.bottom + 12))

            pygame.display.flip()
            clock.tick(FPS)

        if not paused:
            frame_count += 1
            if frame_count >= max(1, int(cfg.max_frames)):
                running = False
                if reason == "quit":
                    reason = "timeout"

    paused_extra = paused_total_ms
    if paused and pause_started_ms > 0:
        paused_extra += max(0, pygame.time.get_ticks() - pause_started_ms)
    elapsed_ms = max(0, pygame.time.get_ticks() - start_ms - paused_extra)
    enemies_remaining = len(enemy_group)
    enemies_killed = max(0, total_enemies - enemies_remaining)
    remaining_enemy_hp = sum(float(getattr(enemy, "health", 0.0)) for enemy in enemy_group)
    damage_dealt = max(0.0, initial_total_enemy_hp - remaining_enemy_hp)

    return SessionResult(
        level_id=cfg.level_id,
        success=bool(success),
        reason=reason,
        enemies_killed=enemies_killed,
        total_enemies=total_enemies,
        objective_complete=objective_complete,
        elapsed_ms=elapsed_ms,
        elapsed_frames=int(frame_count),
        health_left=float(max(0, player.health)),
        player_alive=bool(player.alive),
        damage_dealt=float(damage_dealt),
        max_still_frames=int(max_still_frames),
        distance_moved=float(distance_moved),
        hazard_hits=int(getattr(player, "hazard_hits", 0)),
        oscillation_events=int(oscillation_events),
        trace_points=tuple(trace_points),
        route_hint=tuple(chosen_hint),
    )


def _merge_weights(genome: Genome, menu_cfg: AgentMenuConfig) -> Genome:
    merged = genome.copy()
    merged.genes["aggression"] = float(merged.genes.get("aggression", 1.0)) * float(menu_cfg.weight_aggression)
    merged.genes["survival"] = float(merged.genes.get("survival", 1.0)) * float(menu_cfg.weight_survival)
    merged.genes["objective"] = float(merged.genes.get("objective", 1.0)) * float(menu_cfg.weight_objective)
    base_stalking = float(merged.genes.get("stalking", merged.genes.get("pathing", 1.0)))
    merged.genes["stalking"] = base_stalking * float(menu_cfg.weight_pathing)
    merged.genes["unstuck"] = float(merged.genes.get("unstuck", 1.0)) * float(menu_cfg.weight_pathing)
    return merged


def _fitness_from_result(result: SessionResult) -> float:
    fitness = 0.0
    kill_ratio = float(result.enemies_killed) / max(1.0, float(result.total_enemies))
    sim_seconds = float(result.elapsed_frames) / max(1.0, float(FPS))
    osc_ratio = float(result.oscillation_events) / max(1.0, float(result.elapsed_frames))

    # Prioridad principal: eliminaciones y dano efectivo.
    fitness += float(result.enemies_killed) * 1800.0
    fitness += kill_ratio * 1200.0
    fitness += float(result.damage_dealt) * 6.0

    # Senales intermedias de exploracion/supervivencia.
    fitness += float(result.health_left) * 2.4
    fitness += float(result.distance_moved) * 0.015
    if result.objective_complete:
        fitness += 1100.0
    if result.success:
        fitness += 1400.0
    if not result.player_alive:
        fitness -= 220.0

    # Penalizaciones de navegacion / bloqueo.
    fitness -= float(result.max_still_frames) * 8.0
    fitness -= osc_ratio * 1400.0
    fitness -= float(result.hazard_hits) * 120.0
    fitness -= sim_seconds * 2.5
    if osc_ratio > 0.22:
        fitness -= (osc_ratio - 0.22) * 900.0
    if result.reason == "timeout" and result.enemies_killed == 0:
        fitness -= 320.0
    if result.reason == "timeout":
        missing = max(0, int(result.total_enemies) - int(result.enemies_killed))
        fitness -= float(missing) * 110.0
    if result.enemies_killed <= 0:
        fitness -= 220.0
    return fitness

def _show_info_screen(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    title: str,
    lines: list[str],
    accent=(132, 214, 245),
):
    title_font = pygame.font.SysFont("consolas", 40, bold=True)
    line_font = pygame.font.SysFont("consolas", 22)
    help_font = pygame.font.SysFont("consolas", 18)
    scroll = 0
    line_step = 34
    max_chars = 84

    while True:
        panel = pygame.Rect(84, 92, SCREEN_WIDTH - 168, SCREEN_HEIGHT - 184)
        visible_lines = max(1, (panel.height - 156) // line_step)
        max_scroll = max(0, len(lines) - visible_lines)
        scroll = max(0, min(scroll, max_scroll))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    return
                if event.key in (pygame.K_UP, pygame.K_w):
                    scroll = max(0, scroll - 1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    scroll = min(max_scroll, scroll + 1)
                elif event.key in (pygame.K_PAGEUP, pygame.K_LEFT):
                    scroll = max(0, scroll - visible_lines)
                elif event.key in (pygame.K_PAGEDOWN, pygame.K_RIGHT):
                    scroll = min(max_scroll, scroll + visible_lines)
            if event.type == pygame.MOUSEWHEEL:
                scroll = max(0, min(max_scroll, scroll - int(event.y)))

        screen.fill((12, 20, 26))
        pygame.draw.rect(screen, (18, 34, 44), panel, border_radius=14)
        pygame.draw.rect(screen, accent, panel, width=3, border_radius=14)

        title_surface = title_font.render(title, True, (242, 245, 247))
        screen.blit(title_surface, (panel.x + 24, panel.y + 20))

        visible_slice = lines[scroll : scroll + visible_lines]
        for idx, line in enumerate(visible_slice):
            text = str(line)
            if len(text) > max_chars:
                text = text[: max_chars - 3] + "..."
            line_surface = line_font.render(text, True, (206, 222, 232))
            screen.blit(line_surface, (panel.x + 24, panel.y + 86 + idx * line_step))

        page_text = f"Lineas {scroll + 1}-{min(len(lines), scroll + visible_lines)} / {max(1, len(lines))}"
        page_surface = help_font.render(page_text, True, (174, 204, 218))
        screen.blit(page_surface, (panel.right - page_surface.get_width() - 24, panel.bottom - 64))

        footer = help_font.render(
            "ENTER/ESC salir | UP/DOWN desplazar | PgUp/PgDn pagina",
            True,
            (154, 190, 210),
        )
        screen.blit(footer, (panel.x + 24, panel.bottom - 38))

        pygame.display.flip()
        clock.tick(60)


def _draw_training_progress(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    menu_cfg: AgentMenuConfig,
    generation_idx: int,
    total_generations: int,
    genome_idx: int,
    population_size: int,
    level: str,
    best_fitness: float,
    success_count: int,
    last_result: SessionResult | None,
) -> str | None:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            return "quit"
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "cancel"

    screen.fill((14, 22, 18))
    panel = pygame.Rect(66, 88, SCREEN_WIDTH - 132, SCREEN_HEIGHT - 176)
    pygame.draw.rect(screen, (22, 34, 28), panel, border_radius=14)
    pygame.draw.rect(screen, (158, 198, 142), panel, width=3, border_radius=14)

    title_font = pygame.font.SysFont("consolas", 38, bold=True)
    body_font = pygame.font.SysFont("consolas", 21)
    small_font = pygame.font.SysFont("consolas", 17)

    title = title_font.render("Entrenamiento IA en Progreso", True, (234, 246, 230))
    screen.blit(title, (panel.x + 24, panel.y + 20))

    progress = max(0.0, min(1.0, float(genome_idx + 1) / max(1.0, float(population_size))))
    bar_rect = pygame.Rect(panel.x + 24, panel.y + 76, panel.width - 48, 20)
    pygame.draw.rect(screen, (44, 62, 50), bar_rect, border_radius=8)
    pygame.draw.rect(screen, (202, 230, 146), (bar_rect.x, bar_rect.y, int(bar_rect.width * progress), bar_rect.height), border_radius=8)
    pygame.draw.rect(screen, (132, 162, 126), bar_rect, width=2, border_radius=8)

    lines = [
        f"Nivel: {level}",
        f"Generacion: {generation_idx + 1}/{total_generations}",
        f"Individuo: {genome_idx + 1}/{population_size}",
        f"Poblacion: {menu_cfg.population_size}  |  Seleccion: {menu_cfg.selection_mode}",
        f"Cruce: {menu_cfg.crossover_mode}  |  Mutacion: {menu_cfg.mutation_rate:.2f} x {menu_cfg.mutation_scale:.2f}",
        f"Pesos a/s/o/p: {menu_cfg.weight_aggression:.2f}/{menu_cfg.weight_survival:.2f}/{menu_cfg.weight_objective:.2f}/{menu_cfg.weight_pathing:.2f}",
        f"Mejor fitness global: {best_fitness:.2f}",
        f"Exitos en generacion actual: {success_count}/{max(1, genome_idx + 1)}",
    ]
    if last_result is not None:
        lines.append(
            f"Ultimo resultado -> kills={last_result.enemies_killed}/{last_result.total_enemies}, "
            f"dmg={last_result.damage_dealt:.0f}, stuck={last_result.max_still_frames}f, "
            f"osc={last_result.oscillation_events}, hongos={last_result.hazard_hits}"
        )

    for idx, line in enumerate(lines):
        surf = body_font.render(line, True, (212, 226, 208))
        screen.blit(surf, (panel.x + 24, panel.y + 122 + idx * 34))

    footer = small_font.render("ESC cancela entrenamiento | Ventana activa durante el proceso", True, (166, 190, 160))
    screen.blit(footer, (panel.x + 24, panel.bottom - 36))

    pygame.display.flip()
    clock.tick(60)
    return None


def train_agent(screen: pygame.Surface, clock: pygame.time.Clock, menu_cfg: AgentMenuConfig, runtime_state: RuntimeState):
    level = menu_cfg.training_level
    if level in ("level_2", "level_3"):
        return {
            "title": "Entrenamiento IA",
            "lines": [
                f"Nivel solicitado: {level}",
                "Estado: pendiente (nivel aun no listo)",
                "Tip: usa Sandbox o Nivel 1 para arrancar el entrenamiento.",
            ],
        }

    ga_cfg = GeneticConfig(
        population_size=menu_cfg.population_size,
        generations=menu_cfg.generations,
        crossover_mode=menu_cfg.crossover_mode,
        selection_mode=menu_cfg.selection_mode,
        mutation_rate=menu_cfg.mutation_rate,
        mutation_scale=menu_cfg.mutation_scale,
    )

    rng = random.Random(19)
    seed_genome, seed_hint = _choose_training_seed(level, runtime_state)
    population = create_population(ga_cfg, rng)
    _seed_population_around_genome(population, seed_genome, ga_cfg, rng)

    history_lines: list[str] = []
    detail_lines: list[str] = []
    best_overall = seed_genome.copy() if seed_genome is not None else default_genome()
    best_overall.fitness = -1e9
    best_overall_trace: tuple[tuple[int, int], ...] = _compress_trace_points(seed_hint, min_step=14.0, max_points=320)
    generation_hint: tuple[tuple[int, int], ...] = best_overall_trace
    best_hint_kills = -1
    best_hint_damage = -1.0
    best_hint_stuck = 10**9
    last_result: SessionResult | None = None
    train_max_frames = 12000 if level == "level_1" else 7600
    validation_max_frames = 14000 if level == "level_1" else 9000

    for generation in range(ga_cfg.generations):
        success_count = 0
        gen_results: dict[int, SessionResult] = {}
        for genome_idx, genome in enumerate(population):
            state = _draw_training_progress(
                screen=screen,
                clock=clock,
                menu_cfg=menu_cfg,
                generation_idx=generation,
                total_generations=ga_cfg.generations,
                genome_idx=genome_idx,
                population_size=max(1, len(population)),
                level=level,
                best_fitness=best_overall.fitness,
                success_count=success_count,
                last_result=last_result,
            )
            if state == "quit":
                return {
                    "title": "Entrenamiento IA",
                    "lines": ["Entrenamiento interrumpido por cierre de ventana."],
                }
            if state == "cancel":
                return {
                    "title": "Entrenamiento IA",
                    "lines": ["Entrenamiento cancelado por usuario (ESC)."],
                }
            _apply_level_gene_freeze(genome, level, generation, ga_cfg.generations)
            effective_genome = _merge_weights(genome, menu_cfg)
            _apply_level_gene_freeze(effective_genome, level, generation, ga_cfg.generations)
            result = run_game_session(
                screen,
                clock,
                SessionConfig(
                    level_id=level,
                    manual=False,
                    use_agent=True,
                    sandbox_enemy_count=menu_cfg.sandbox_enemy_count,
                    render=False,
                    max_frames=train_max_frames,
                    agent_genome=effective_genome,
                    path_hint=None,
                ),
            )
            genome.fitness = _fitness_from_result(result)
            gen_results[id(genome)] = result
            last_result = result
            detail_lines.append(
                f"gen={generation + 1}/{ga_cfg.generations} | ind={genome_idx + 1}/{len(population)} | "
                f"fit={genome.fitness:.2f} | kills={result.enemies_killed}/{result.total_enemies} | "
                f"dmg={result.damage_dealt:.0f} | "
                f"sim_t={result.elapsed_frames / max(1.0, float(FPS)):.2f}s | real_t={result.elapsed_ms / 1000.0:.2f}s | "
                f"frames={result.elapsed_frames} | "
                f"stuck={result.max_still_frames}f | osc={result.oscillation_events} | hongos={result.hazard_hits} | "
                f"ok={'SI' if result.success else 'NO'} | motivo={result.reason}"
            )
            if result.success:
                success_count += 1

        ranked = sorted(population, key=lambda g: g.fitness, reverse=True)
        gen_best = ranked[0]
        best_result = gen_results.get(id(gen_best))
        gen_success_rate = (success_count / max(1, len(ranked))) * 100.0
        if best_result is None:
            history_lines.append(
                f"Gen {generation + 1}: best={gen_best.fitness:.1f} | success={gen_success_rate:.0f}%"
            )
        else:
            history_lines.append(
                "Gen "
                f"{generation + 1}: best={gen_best.fitness:.1f} | "
                f"kills={best_result.enemies_killed}/{best_result.total_enemies} | "
                f"dmg={best_result.damage_dealt:.0f} | "
                f"stuck={best_result.max_still_frames}f | osc={best_result.oscillation_events} | "
                f"hongos={best_result.hazard_hits} | success={gen_success_rate:.0f}%"
            )

        if gen_best.fitness > best_overall.fitness:
            best_overall = gen_best.copy()
            if best_result is not None:
                hint_source = best_result.route_hint or best_result.trace_points
                if hint_source:
                    best_overall_trace = _compress_trace_points(hint_source, min_step=14.0, max_points=320)
        if best_result is not None:
            hint_source = best_result.route_hint or best_result.trace_points
            candidate_hint = _compress_trace_points(hint_source, min_step=14.0, max_points=320) if hint_source else ()
            better_hint = (
                best_result.enemies_killed > best_hint_kills
                or (
                    best_result.enemies_killed == best_hint_kills
                    and (
                        best_result.damage_dealt > best_hint_damage
                        or (
                            abs(best_result.damage_dealt - best_hint_damage) <= 1e-6
                            and best_result.max_still_frames < best_hint_stuck
                        )
                    )
                )
            )
            if candidate_hint and better_hint:
                generation_hint = candidate_hint
                best_hint_kills = int(best_result.enemies_killed)
                best_hint_damage = float(best_result.damage_dealt)
                best_hint_stuck = int(best_result.max_still_frames)

        population = evolve_population(ranked, ga_cfg, rng)
        if population:
            # Persistimos el mejor global sin mutar para estabilizar aprendizaje entre generaciones.
            population[0] = best_overall.copy()
            _apply_level_gene_freeze(population[0], level, generation + 1, ga_cfg.generations)

    runtime_state.best_genome = _merge_weights(best_overall, menu_cfg)
    runtime_state.best_path_hint = tuple(best_overall_trace)
    if runtime_state.best_genome_by_level is None:
        runtime_state.best_genome_by_level = {}
    if runtime_state.best_path_hint_by_level is None:
        runtime_state.best_path_hint_by_level = {}
    runtime_state.best_genome_by_level[level] = runtime_state.best_genome.copy()
    runtime_state.best_path_hint_by_level[level] = tuple(best_overall_trace)

    validation = run_game_session(
        screen,
        clock,
        SessionConfig(
            level_id=level,
            manual=False,
            use_agent=True,
            sandbox_enemy_count=menu_cfg.sandbox_enemy_count,
            render=False,
            max_frames=validation_max_frames,
            agent_genome=runtime_state.best_genome,
            path_hint=None,
        ),
    )

    status = "PASO" if validation.success else "NO PASO"
    history_lines.append(
        "Validacion final: "
        f"{status} | kills={validation.enemies_killed}/{validation.total_enemies} | "
        f"dmg={validation.damage_dealt:.0f} | "
        f"sim_t={validation.elapsed_frames / max(1.0, float(FPS)):.1f}s | real_t={validation.elapsed_ms / 1000.0:.1f}s | "
        f"stuck_max={validation.max_still_frames}f | osc={validation.oscillation_events} | hongos={validation.hazard_hits}"
    )

    report_path = _save_training_txt(
        level=level,
        menu_cfg=menu_cfg,
        summary_lines=history_lines,
        detail_lines=detail_lines,
    )
    if report_path is not None:
        history_lines.append(f"TXT guardado: {report_path}")
    else:
        history_lines.append("TXT guardado: error al exportar reporte")

    if validation.success:
        profile_path = _save_winning_profile(
            runtime_state=runtime_state,
            menu_cfg=menu_cfg,
            level_id=level,
            source="training_validation",
        )
        if profile_path is not None:
            history_lines.append(f"Perfil ganador guardado: {profile_path}")
        else:
            history_lines.append("Perfil ganador guardado: error al exportar preset")

    output_lines = [
        f"Nivel: {level}",
        f"Poblacion: {ga_cfg.population_size} | Generaciones: {ga_cfg.generations}",
        f"Mejor fitness: {best_overall.fitness:.2f}",
    ]
    output_lines.extend(history_lines[-6:])
    return {
        "title": "Entrenamiento IA",
        "lines": output_lines,
    }


def _save_training_txt(
    level: str,
    menu_cfg: AgentMenuConfig,
    summary_lines: list[str],
    detail_lines: list[str],
) -> str | None:
    report_dir = Path("training_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"training_{level}_{stamp}.txt"

    try:
        with report_path.open("w", encoding="utf-8") as handle:
            handle.write("Atraco Tactico - Reporte de Entrenamiento IA\n")
            handle.write(f"Fecha: {datetime.now().isoformat(timespec='seconds')}\n")
            handle.write(f"Nivel: {level}\n")
            handle.write(
                "Config: "
                f"poblacion={menu_cfg.population_size}, generaciones={menu_cfg.generations}, "
                f"seleccion={menu_cfg.selection_mode}, cruce={menu_cfg.crossover_mode}, "
                f"mutacion={menu_cfg.mutation_rate:.2f}x{menu_cfg.mutation_scale:.2f}, "
                f"pesos(a/s/o/p)={menu_cfg.weight_aggression:.2f}/{menu_cfg.weight_survival:.2f}/"
                f"{menu_cfg.weight_objective:.2f}/{menu_cfg.weight_pathing:.2f}\n"
            )
            handle.write("\nResumen:\n")
            for line in summary_lines:
                handle.write(f"- {line}\n")
            handle.write("\nDetalle por individuo:\n")
            for line in detail_lines:
                handle.write(f"- {line}\n")
    except Exception:
        return None

    return str(report_path)


def _save_benchmark_txt(summary_lines: list[str], detail_lines: list[str], episodes: int) -> str | None:
    report_dir = Path("benchmark_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"benchmark_{stamp}.txt"

    try:
        with report_path.open("w", encoding="utf-8") as handle:
            handle.write("Atraco Tactico - Benchmark IA\n")
            handle.write(f"Fecha: {datetime.now().isoformat(timespec='seconds')}\n")
            handle.write(f"Corridas por nivel: {episodes}\n")
            handle.write("\nResumen:\n")
            for line in summary_lines:
                handle.write(f"- {line}\n")
            handle.write("\nDetalle por corrida:\n")
            for line in detail_lines:
                handle.write(f"- {line}\n")
    except Exception:
        return None

    return str(report_path)


def run_benchmark(screen: pygame.Surface, clock: pygame.time.Clock, menu_cfg: AgentMenuConfig, runtime_state: RuntimeState):
    base_genome = runtime_state.best_genome if runtime_state.best_genome is not None else default_genome()
    base_path_hint = tuple(getattr(runtime_state, "best_path_hint", ()))

    lines = []
    detail_lines: list[str] = []
    levels = ["level_1", "level_2", "level_3"]
    episodes = max(1, int(menu_cfg.benchmark_runs))

    for level in levels:
        if level in ("level_2", "level_3"):
            lines.append(f"{level}: pendiente (sin mapa definitivo)")
            detail_lines.append(f"{level}: sin ejecucion (nivel pendiente)")
            continue

        wins = 0
        total_kills = 0
        total_enemy = 0
        total_time = 0
        total_damage = 0.0
        total_stuck = 0
        total_osc = 0
        total_hazards = 0

        for run_idx in range(episodes):
            by_level_gen = runtime_state.best_genome_by_level or {}
            by_level_hint = runtime_state.best_path_hint_by_level or {}
            level_genome = by_level_gen.get(level, base_genome)
            level_hint = tuple(by_level_hint.get(level, base_path_hint))
            result = run_game_session(
                screen,
                clock,
                SessionConfig(
                    level_id=level,
                    manual=False,
                    use_agent=True,
                    sandbox_enemy_count=menu_cfg.sandbox_enemy_count,
                    render=False,
                    max_frames=14000 if level == "level_1" else 9000,
                    agent_genome=level_genome,
                    path_hint=None,
                ),
            )
            wins += 1 if result.success else 0
            total_kills += result.enemies_killed
            total_enemy += max(1, result.total_enemies)
            total_time += result.elapsed_ms
            total_damage += result.damage_dealt
            total_stuck += result.max_still_frames
            total_osc += result.oscillation_events
            total_hazards += result.hazard_hits
            detail_lines.append(
                f"{level} | corrida={run_idx + 1}/{episodes} | paso={'SI' if result.success else 'NO'} | "
                f"motivo={result.reason} | enemigos={result.enemies_killed}/{result.total_enemies} | "
                f"dano={result.damage_dealt:.0f} | tiempo={result.elapsed_ms / 1000.0:.2f}s | frames={result.elapsed_frames} | "
                f"stuck={result.max_still_frames}f | osc={result.oscillation_events} | hongos={result.hazard_hits}"
            )

        success_rate = (wins / episodes) * 100.0
        avg_kills = (total_kills / total_enemy) * 100.0
        avg_time = (total_time / episodes) / 1000.0
        avg_damage = total_damage / episodes
        avg_stuck = total_stuck / episodes
        avg_osc = total_osc / episodes
        avg_hazards = total_hazards / episodes
        lines.append(
            f"{level}: win={success_rate:.0f}% | avance={avg_kills:.0f}% | dmg={avg_damage:.0f} | "
            f"tiempo={avg_time:.1f}s | stuck={avg_stuck:.0f}f | osc={avg_osc:.0f} | hongos={avg_hazards:.1f}"
        )

    report_path = _save_benchmark_txt(lines, detail_lines, episodes)
    if report_path is not None:
        lines.append(f"TXT guardado: {report_path}")
    else:
        lines.append("TXT guardado: error al exportar reporte")

    return {
        "title": "Benchmark IA",
        "lines": lines,
    }


def _run_manual_or_agent_session(screen, clock, menu_cfg: AgentMenuConfig, runtime_state: RuntimeState, level_id: str, use_agent: bool, backoffice_overlay: bool):
    genome = None
    path_hint = None
    if use_agent:
        by_level_gen = runtime_state.best_genome_by_level or {}
        by_level_hint = runtime_state.best_path_hint_by_level or {}
        genome = by_level_gen.get(level_id, runtime_state.best_genome)
        path_hint = tuple(by_level_hint.get(level_id, getattr(runtime_state, "best_path_hint", ())))
    result = run_game_session(
        screen,
        clock,
        SessionConfig(
            level_id=level_id,
            manual=not use_agent,
            use_agent=use_agent,
            sandbox_enemy_count=menu_cfg.sandbox_enemy_count,
            render=True,
            max_frames=20000,
            agent_genome=genome,
            path_hint=None,
            backoffice_overlay=backoffice_overlay,
            population_preview=menu_cfg.population_size,
            generation_preview=menu_cfg.generations,
            selection_preview=menu_cfg.selection_mode,
            crossover_preview=menu_cfg.crossover_mode,
        ),
    )

    saved_profile_path: str | None = None
    if use_agent and result.success:
        winner_genome = genome if genome is not None else runtime_state.best_genome
        _register_runtime_winner(
            runtime_state=runtime_state,
            level_id=level_id,
            genome=winner_genome,
            path_hint=tuple(path_hint or ()),
        )
        saved_profile_path = _save_winning_profile(
            runtime_state=runtime_state,
            menu_cfg=menu_cfg,
            level_id=level_id,
            source="agent_demo",
        )

    status = "Mision completada" if result.success else "Sesion finalizada"
    lines = [
        f"Nivel: {result.level_id}",
        f"Resultado: {status}",
        f"Motivo: {result.reason}",
        f"Enemigos: {result.enemies_killed}/{result.total_enemies}",
        f"Dano infligido: {result.damage_dealt:.0f}",
        f"Golpes por hongos: {result.hazard_hits}",
        f"Tiempo: {result.elapsed_ms / 1000.0:.1f}s ({result.elapsed_frames} frames)",
    ]
    if saved_profile_path is not None:
        lines.append(f"Preset ganador guardado: {saved_profile_path}")
    _show_info_screen(screen, clock, "Resultado", lines)


def main() -> str:
    pygame.init()
    try:
        pygame.mixer.init()
    except Exception:
        pass

    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(SCREEN_TITLE)
    clock = pygame.time.Clock()

    menu_cfg = AgentMenuConfig()
    runtime_state = RuntimeState(
        best_genome=default_genome(),
        best_path_hint=(),
        best_genome_by_level={},
        best_path_hint_by_level={},
    )
    menu_cfg, _ = _load_winning_profile(runtime_state, menu_cfg)

    while True:
        menu_result: MenuResult = run_main_menu(screen, clock, menu_cfg)
        menu_cfg = menu_result.config.copy()
        action = menu_result.action

        if action == "quit":
            break

        if action == "play_level_1":
            _run_manual_or_agent_session(screen, clock, menu_cfg, runtime_state, "level_1", use_agent=False, backoffice_overlay=False)
            continue

        if action == "play_sandbox":
            _run_manual_or_agent_session(screen, clock, menu_cfg, runtime_state, "sandbox", use_agent=False, backoffice_overlay=False)
            continue

        if action == "play_agent_level_1":
            _run_manual_or_agent_session(screen, clock, menu_cfg, runtime_state, "level_1", use_agent=True, backoffice_overlay=True)
            continue

        if action == "play_agent_sandbox":
            _run_manual_or_agent_session(screen, clock, menu_cfg, runtime_state, "sandbox", use_agent=True, backoffice_overlay=True)
            continue

        if action == "backoffice_demo":
            demo_level = menu_cfg.training_level
            if demo_level in ("level_2", "level_3"):
                _show_info_screen(
                    screen,
                    clock,
                    "Backoffice Demo",
                    [
                        f"Nivel seleccionado: {demo_level}",
                        "Este nivel aun no esta listo.",
                        "Cambia a Nivel 1 o Sandbox para demo real del agente.",
                    ],
                )
            else:
                _run_manual_or_agent_session(
                    screen,
                    clock,
                    menu_cfg,
                    runtime_state,
                    demo_level,
                    use_agent=True,
                    backoffice_overlay=True,
                )
            continue

        if action == "train_agent":
            report = train_agent(screen, clock, menu_cfg, runtime_state)
            _show_info_screen(screen, clock, report["title"], report["lines"])
            continue

        if action == "run_benchmark":
            report = run_benchmark(screen, clock, menu_cfg, runtime_state)
            _show_info_screen(screen, clock, report["title"], report["lines"])
            continue

        if action == "level_2_placeholder":
            _show_info_screen(
                screen,
                clock,
                "Nivel 2",
                [
                    "Nivel en construccion.",
                    "Ya esta conectado al benchmark/backoffice como pendiente.",
                ],
            )
            continue

        if action == "level_3_placeholder":
            _show_info_screen(
                screen,
                clock,
                "Nivel 3",
                [
                    "Nivel en construccion.",
                    "Ya esta conectado al benchmark/backoffice como pendiente.",
                ],
            )
            continue

        _show_info_screen(
            screen,
            clock,
            "Accion no reconocida",
            [f"No se pudo ejecutar la accion: {action}"],
        )

    pygame.quit()
    return "quit"


if __name__ == "__main__":
    main()
    sys.exit()
