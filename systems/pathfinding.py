from __future__ import annotations

from heapq import heappop, heappush

import pygame

_WALKABLE_CACHE: dict[tuple[int, int, int, int, int, int], set[tuple[int, int]]] = {}


def _dynamic_signature(dynamic_blockers: list[pygame.Rect]) -> int:
    if not dynamic_blockers:
        return 0
    acc = len(dynamic_blockers) * 1315423911
    for rect in dynamic_blockers:
        acc ^= ((int(rect.x) * 73856093) ^ (int(rect.y) * 19349663) ^ (int(rect.w) * 83492791) ^ (int(rect.h) * 2654435761))
        acc &= 0xFFFFFFFF
    return int(acc)

def _tile_probe_rect(tx: int, ty: int, tile_w: int, tile_h: int, ratio: float = 0.52) -> pygame.Rect:
    cx = tx * tile_w + (tile_w // 2)
    cy = ty * tile_h + (tile_h // 2)
    side = max(8, int(min(tile_w, tile_h) * ratio))
    half = side // 2
    return pygame.Rect(cx - half, cy - half, side, side)


def _is_walkable_tile(
    game_map,
    tx: int,
    ty: int,
    tiles_x: int,
    tiles_y: int,
    tile_w: int,
    tile_h: int,
    sample_mask: pygame.mask.Mask,
    dynamic_blockers: list[pygame.Rect],
) -> bool:
    if tx < 0 or ty < 0 or tx >= tiles_x or ty >= tiles_y:
        return False

    probe = _tile_probe_rect(tx, ty, tile_w, tile_h, ratio=0.52)
    cx, cy = probe.center

    if hasattr(game_map, "is_inside_play_area") and not game_map.is_inside_play_area(float(cx), float(cy), margin=0):
        return False

    collision_mask = getattr(game_map, "collision_mask", None)
    if collision_mask is not None:
        if collision_mask.overlap(sample_mask, (probe.x, probe.y)) is not None:
            return False
    else:
        for rect in getattr(game_map, "collision_rects", []):
            if probe.colliderect(rect):
                return False

    for rect in dynamic_blockers:
        if probe.colliderect(rect):
            return False

    return True


def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def _neighbors(tile: tuple[int, int]) -> tuple[tuple[int, int], ...]:
    tx, ty = tile
    return (
        (tx + 1, ty),
        (tx - 1, ty),
        (tx, ty + 1),
        (tx, ty - 1),
    )


def _nearest_walkable(
    origin: tuple[int, int],
    walkable: set[tuple[int, int]],
    max_radius: int = 7,
) -> tuple[int, int] | None:
    if origin in walkable:
        return origin
    ox, oy = origin
    for r in range(1, max_radius + 1):
        for dx in range(-r, r + 1):
            for dy in range(-r, r + 1):
                if abs(dx) != r and abs(dy) != r:
                    continue
                candidate = (ox + dx, oy + dy)
                if candidate in walkable:
                    return candidate
    return None


def astar_tiles(
    walkable: set[tuple[int, int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    max_nodes: int = 24000,
) -> list[tuple[int, int]]:
    if not walkable:
        return []

    start_ok = _nearest_walkable(start, walkable)
    goal_ok = _nearest_walkable(goal, walkable)
    if start_ok is None or goal_ok is None:
        return []

    if start_ok == goal_ok:
        return [start_ok]

    open_heap: list[tuple[int, int, tuple[int, int]]] = []
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    g_score: dict[tuple[int, int], int] = {start_ok: 0}
    visited = set()

    counter = 0
    heappush(open_heap, (_heuristic(start_ok, goal_ok), 0, start_ok))

    while open_heap and counter < max_nodes:
        _, cur_g, current = heappop(open_heap)
        counter += 1
        if current in visited:
            continue
        visited.add(current)

        if current == goal_ok:
            path: list[tuple[int, int]] = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path

        for nxt in _neighbors(current):
            if nxt not in walkable:
                continue
            tentative_g = cur_g + 1
            old = g_score.get(nxt)
            if old is not None and tentative_g >= old:
                continue
            came_from[nxt] = current
            g_score[nxt] = tentative_g
            f = tentative_g + _heuristic(nxt, goal_ok)
            heappush(open_heap, (f, tentative_g, nxt))

    return []


def build_route_hint(
    game_map,
    start_world: tuple[int, int],
    goal_world_points: list[tuple[int, int]],
    max_points: int = 320,
) -> tuple[tuple[int, int], ...]:
    tile_w = int(getattr(game_map, "tile_w", 32) or 32)
    tile_h = int(getattr(game_map, "tile_h", 32) or 32)
    map_w = int(getattr(game_map, "map_width", 0) or 0)
    map_h = int(getattr(game_map, "map_height", 0) or 0)
    if map_w <= 0 or map_h <= 0:
        return ()

    tiles_x = max(1, map_w // tile_w)
    tiles_y = max(1, map_h // tile_h)
    dynamic_blockers = list(game_map.get_dynamic_collisions()) if hasattr(game_map, "get_dynamic_collisions") else []
    dyn_sig = _dynamic_signature(dynamic_blockers)

    cache_key = (id(game_map), map_w, map_h, tile_w, tile_h, dyn_sig)
    walkable = _WALKABLE_CACHE.get(cache_key)
    if walkable is None:
        sample_side = max(6, int(min(tile_w, tile_h) * 0.52))
        sample_mask = pygame.mask.Mask((sample_side, sample_side), fill=True)

        walkable = set()
        for ty in range(tiles_y):
            for tx in range(tiles_x):
                if _is_walkable_tile(
                    game_map,
                    tx,
                    ty,
                    tiles_x,
                    tiles_y,
                    tile_w,
                    tile_h,
                    sample_mask,
                    dynamic_blockers,
                ):
                    walkable.add((tx, ty))
        _WALKABLE_CACHE[cache_key] = walkable

    if not walkable:
        return ()

    sx, sy = int(start_world[0]), int(start_world[1])
    current = (sx // tile_w, sy // tile_h)

    remaining_goals = [(int(x), int(y)) for x, y in goal_world_points]
    if not remaining_goals:
        return ()

    hint_world: list[tuple[int, int]] = []
    safety = 0
    while remaining_goals and safety < 10:
        safety += 1
        remaining_goals.sort(key=lambda g: abs((g[0] // tile_w) - current[0]) + abs((g[1] // tile_h) - current[1]))
        gx, gy = remaining_goals.pop(0)
        goal_tile = (gx // tile_w, gy // tile_h)
        tile_path = astar_tiles(walkable, current, goal_tile)
        if not tile_path:
            continue
        for tx, ty in tile_path:
            wx = tx * tile_w + (tile_w // 2)
            wy = ty * tile_h + (tile_h // 2)
            if not hint_world or abs(wx - hint_world[-1][0]) + abs(wy - hint_world[-1][1]) >= max(6, min(tile_w, tile_h) // 2):
                hint_world.append((wx, wy))
                if len(hint_world) >= max_points:
                    return tuple(hint_world[:max_points])
        current = tile_path[-1]

    return tuple(hint_world[:max_points])
