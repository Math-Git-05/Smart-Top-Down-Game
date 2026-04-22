# ============================================================
#  infrastructure/map_loader.py - Carga mapas de Tiled (.tmx)
# ============================================================

import pygame
import pytmx
from pytmx.util_pygame import load_pygame

from config.settings import (
    LAYER_COLLISIONS,
    LAYER_HONGOS,
    LAYER_WATER,
    MAP_RENDER_LAYERS_OVER_PLAYER,
    MAP_RENDER_LAYERS_UNDER_PLAYER,
    MAP_TILED_LAYER_ORDER,
    LAYER_PUERTA_CLOSED,
    LAYER_COFRE_CLOSED,
)


class MapLoader:
    """
    Carga un archivo .tmx y expone:
      - layer_surfaces: superficies por capa (sin la capa collisions)
      - collision_rects: lista de pygame.Rect bloqueados
      - map_width / map_height: dimensiones en px
      - layers_under_player / layers_over_player: orden de render por grupos
    """

    def __init__(self, tmx_path: str):
        self.tmx_data = load_pygame(tmx_path)
        self.tile_w = self.tmx_data.tilewidth
        self.tile_h = self.tmx_data.tileheight
        self.map_width = self.tmx_data.width * self.tile_w
        self.map_height = self.tmx_data.height * self.tile_h

        self._all_layers = list(self.tmx_data.layers)
        self._tile_layer_names = self._discover_tile_layer_names()
        self.water_ref = next(
            (
                name
                for name in self._tile_layer_names
                if self._normalize_layer_name(name) == self._normalize_layer_name(LAYER_WATER)
            ),
            LAYER_WATER,
        )
        self.layer_surfaces = self._build_layer_surfaces()
        self.layers_under_player, self.layers_over_player = self._resolve_render_groups()
        
        # Diccionario para permitir ocultar/mostrar capas dinámicamente
        self.layer_visible = {layer: True for layer in self.layer_surfaces}
        self.collision_sources: list[dict] = []

        self.collision_rects = self._build_collision_rects()
        self.hazard_rects = self._build_hazard_rects()
        self.hazard_centers = [rect.center for rect in self.hazard_rects]
        self.dynamic_layer_rects = self._build_layer_rects()
        self.collision_mask = self._build_collision_mask()

    @staticmethod
    def _is_layer_visible(layer, fallback_visible: bool = True) -> bool:
        visible = getattr(layer, "visible", None)
        if visible is None:
            return bool(fallback_visible)
        try:
            return bool(int(visible))
        except Exception:
            return bool(visible)

    @staticmethod
    def _normalize_layer_name(name: str) -> str:
        return str(name or "").strip().lower()

    def _is_collision_layer_name(self, layer_name: str) -> bool:
        return self._normalize_layer_name(layer_name) == self._normalize_layer_name(LAYER_COLLISIONS)

    @staticmethod
    def _extract_xy(point) -> tuple[float, float]:
        if hasattr(point, "x") and hasattr(point, "y"):
            return float(point.x), float(point.y)
        if isinstance(point, (tuple, list)) and len(point) >= 2:
            return float(point[0]), float(point[1])
        return 0.0, 0.0

    def _score_points_in_map(self, points: list[tuple[float, float]]) -> int:
        max_x = float(self.map_width)
        max_y = float(self.map_height)
        return sum(1 for x, y in points if 0.0 <= x <= max_x and 0.0 <= y <= max_y)

    def _normalize_object_polygon(self, obj, points) -> list[tuple[float, float]]:
        raw_points = [self._extract_xy(p) for p in points]
        ox = float(getattr(obj, "x", 0.0) or 0.0)
        oy = float(getattr(obj, "y", 0.0) or 0.0)
        offset_points = [(x + ox, y + oy) for x, y in raw_points]

        # Compatibilidad: algunos loaders reportan puntos absolutos, otros relativos al objeto.
        if self._score_points_in_map(offset_points) >= self._score_points_in_map(raw_points):
            return offset_points
        return raw_points

    def _get_tile_layer(self, layer_name: str):
        try:
            layer = self.tmx_data.get_layer_by_name(layer_name)
        except (ValueError, KeyError):
            layer = None
        if isinstance(layer, pytmx.TiledTileLayer):
            return layer
        normalized_target = self._normalize_layer_name(layer_name)
        for candidate in getattr(self.tmx_data, "layers", []):
            if not isinstance(candidate, pytmx.TiledTileLayer):
                continue
            if self._normalize_layer_name(getattr(candidate, "name", "")) == normalized_target:
                return candidate
        return None

    def _discover_tile_layer_names(self) -> list[str]:
        names: list[str] = []
        for layer in self._all_layers:
            if not isinstance(layer, pytmx.TiledTileLayer):
                continue
            layer_name = str(getattr(layer, "name", "") or "").strip()
            if not layer_name:
                continue
            if self._is_collision_layer_name(layer_name):
                continue
            if layer_name not in names:
                names.append(layer_name)
        return names

    def _looks_over_layer(self, layer_name: str) -> bool:
        norm = self._normalize_layer_name(layer_name)
        return ("over" in norm) or norm.endswith("-over") or norm.startswith("overlay")

    def _resolve_render_groups(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        known_under = [name for name in MAP_RENDER_LAYERS_UNDER_PLAYER if name in self.layer_surfaces]
        known_over = [name for name in MAP_RENDER_LAYERS_OVER_PLAYER if name in self.layer_surfaces]
        used = set(known_under + known_over)

        for name in self._tile_layer_names:
            if name not in self.layer_surfaces or name in used:
                continue
            if self._looks_over_layer(name):
                known_over.append(name)
            else:
                known_under.append(name)
            used.add(name)

        if not known_under and not known_over:
            for name in self._tile_layer_names:
                if name not in self.layer_surfaces:
                    continue
                if self._looks_over_layer(name):
                    known_over.append(name)
                else:
                    known_under.append(name)
        return tuple(known_under), tuple(known_over)

    def _build_layer_surface(self, tile_layer: pytmx.TiledTileLayer) -> pygame.Surface:
        surf = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)
        for x, y, gid in tile_layer:
            if not gid:
                continue
            tile = self.tmx_data.get_tile_image_by_gid(gid)
            if tile:
                surf.blit(tile, (x * self.tile_w, y * self.tile_h))
        return surf

    def _build_layer_surfaces(self) -> dict[str, pygame.Surface]:
        surfaces = {}
        ordered_names: list[str] = []
        for layer_name in MAP_TILED_LAYER_ORDER:
            if layer_name == LAYER_COLLISIONS:
                continue
            if layer_name not in ordered_names:
                ordered_names.append(layer_name)
        for layer_name in self._tile_layer_names:
            if layer_name not in ordered_names:
                ordered_names.append(layer_name)

        for layer_name in ordered_names:
            tile_layer = self._get_tile_layer(layer_name)
            if tile_layer is None:
                continue
            surfaces[layer_name] = self._build_layer_surface(tile_layer)
        return surfaces

    def draw_layers(
        self,
        target_surface: pygame.Surface,
        layer_names: tuple[str, ...] | list[str],
        offset: tuple[int, int] = (0, 0),
    ):
        ox, oy = offset
        for layer_name in layer_names:
            if not getattr(self, "layer_visible", {}).get(layer_name, True):
                continue
                
            layer_surface = self.layer_surfaces.get(layer_name)
            if layer_surface is not None:
                if layer_name == getattr(self, 'water_ref', "agua"):
                    # Animación infinita estilo cascada para el agua
                    current_time = pygame.time.get_ticks()
                    px_offset = (current_time / 45.0) % self.tile_w
                    
                    # Dibujamos iterativamente para cubrir los huecos de la animación
                    target_surface.blit(layer_surface, (-ox + px_offset, -oy))
                    target_surface.blit(layer_surface, (-ox + px_offset - self.map_width, -oy))
                else:
                    target_surface.blit(layer_surface, (-ox, -oy))

    def _build_collision_rects(self) -> list[pygame.Rect]:
        rects = []
        self.debug_tile_col = []
        self.debug_obj_col = []
        self.debug_obj_polygons: list[list[tuple[int, int]]] = []

        col_layer = self._get_tile_layer(LAYER_COLLISIONS)
        if col_layer is not None:
            for x, y, gid in col_layer:
                if gid:
                    r = pygame.Rect(
                            x * self.tile_w,
                            y * self.tile_h,
                            self.tile_w,
                            self.tile_h,
                        )
                    rects.append(r)
                    self.debug_tile_col.append(r)
                    self.collision_sources.append(
                        {
                            "kind": "rect",
                            "layer": LAYER_COLLISIONS,
                            "id": f"tile:{x},{y}",
                            "rect": r.copy(),
                        }
                    )

        for layer in self.tmx_data.objectgroups:
            if not self._is_collision_layer_name(getattr(layer, "name", "")):
                continue
            for obj in layer:
                if hasattr(obj, 'points') and obj.points:
                    normalized = self._normalize_object_polygon(obj, obj.points)
                    if len(normalized) >= 3:
                        self.debug_obj_polygons.append([(int(x), int(y)) for x, y in normalized])
                        min_x = min(p[0] for p in normalized)
                        min_y = min(p[1] for p in normalized)
                        max_x = max(p[0] for p in normalized)
                        max_y = max(p[1] for p in normalized)
                        self.collision_sources.append(
                            {
                                "kind": "polygon",
                                "layer": layer.name,
                                "id": f"obj:{getattr(obj, 'id', '?')}",
                                "points": [(float(x), float(y)) for x, y in normalized],
                                "bbox": pygame.Rect(
                                    int(min_x),
                                    int(min_y),
                                    max(1, int(max_x - min_x)),
                                    max(1, int(max_y - min_y)),
                                ),
                            }
                        )
                    xs = [p[0] for p in normalized]
                    ys = [p[1] for p in normalized]
                    rx = min(xs)
                    ry = min(ys)
                    rw = max(xs) - rx
                    rh = max(ys) - ry
                else:
                    rx = obj.x
                    ry = obj.y
                    rw = getattr(obj, "width", 0) or self.tile_w
                    rh = getattr(obj, "height", 0) or self.tile_h
                
                r = pygame.Rect(int(rx), int(ry), int(max(rw, 1)), int(max(rh, 1)))
                rects.append(r)
                self.debug_obj_col.append(r)
                if not (hasattr(obj, 'points') and obj.points and len(obj.points) >= 3):
                    self.collision_sources.append(
                        {
                            "kind": "rect",
                            "layer": layer.name,
                            "id": f"obj:{getattr(obj, 'id', '?')}",
                            "rect": r.copy(),
                        }
                    )
        return rects

    @staticmethod
    def _point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
        inside = False
        n = len(polygon)
        if n < 3:
            return False
        j = n - 1
        for i in range(n):
            xi, yi = polygon[i]
            xj, yj = polygon[j]
            if (yi > y) != (yj > y):
                x_cross = ((xj - xi) * (y - yi) / ((yj - yi) if (yj - yi) != 0 else 1e-9)) + xi
                if x < x_cross:
                    inside = not inside
            j = i
        return inside

    @staticmethod
    def _segments_intersect(a1, a2, b1, b2) -> bool:
        def ccw(p1, p2, p3):
            return (p3[1] - p1[1]) * (p2[0] - p1[0]) > (p2[1] - p1[1]) * (p3[0] - p1[0])

        return ccw(a1, b1, b2) != ccw(a2, b1, b2) and ccw(a1, a2, b1) != ccw(a1, a2, b2)

    def _polygon_intersects_rect(self, polygon: list[tuple[float, float]], rect: pygame.Rect) -> bool:
        if not polygon:
            return False

        # Rect corners inside polygon.
        corners = [
            (float(rect.left), float(rect.top)),
            (float(rect.right - 1), float(rect.top)),
            (float(rect.left), float(rect.bottom - 1)),
            (float(rect.right - 1), float(rect.bottom - 1)),
        ]
        if any(self._point_in_polygon(cx, cy, polygon) for cx, cy in corners):
            return True

        # Polygon points inside rect.
        if any(rect.collidepoint(int(px), int(py)) for px, py in polygon):
            return True

        # Edge intersection.
        rect_edges = [
            ((rect.left, rect.top), (rect.right - 1, rect.top)),
            ((rect.right - 1, rect.top), (rect.right - 1, rect.bottom - 1)),
            ((rect.right - 1, rect.bottom - 1), (rect.left, rect.bottom - 1)),
            ((rect.left, rect.bottom - 1), (rect.left, rect.top)),
        ]
        n = len(polygon)
        for i in range(n):
            p1 = polygon[i]
            p2 = polygon[(i + 1) % n]
            for e1, e2 in rect_edges:
                if self._segments_intersect(p1, p2, e1, e2):
                    return True
        return False

    def _object_contains_point(self, obj, x: float, y: float) -> bool:
        points = getattr(obj, "points", None)
        if points and len(points) >= 3:
            polygon = self._normalize_object_polygon(obj, points)
            return self._point_in_polygon(x, y, polygon)

        if bool(getattr(obj, "ellipse", False)):
            rx = float(getattr(obj, "x", 0.0) or 0.0)
            ry = float(getattr(obj, "y", 0.0) or 0.0)
            rw = float(getattr(obj, "width", 0.0) or 0.0)
            rh = float(getattr(obj, "height", 0.0) or 0.0)
            if rw <= 0.0 or rh <= 0.0:
                return False
            cx = rx + (rw / 2.0)
            cy = ry + (rh / 2.0)
            nx = (x - cx) / (rw / 2.0)
            ny = (y - cy) / (rh / 2.0)
            return (nx * nx + ny * ny) <= 1.0

        rx = float(getattr(obj, "x", 0.0) or 0.0)
        ry = float(getattr(obj, "y", 0.0) or 0.0)
        rw = float(getattr(obj, "width", 0.0) or 0.0)
        rh = float(getattr(obj, "height", 0.0) or 0.0)
        if rw <= 0.0:
            rw = float(self.tile_w)
        if rh <= 0.0:
            rh = float(self.tile_h)
        return (rx <= x <= (rx + rw)) and (ry <= y <= (ry + rh))

    def get_layers_at_world_point(self, world_x: float, world_y: float, include_hidden: bool = True) -> list[str]:
        x = float(world_x)
        y = float(world_y)
        if x < 0.0 or y < 0.0 or x >= float(self.map_width) or y >= float(self.map_height):
            return []

        tx = int(x) // int(self.tile_w)
        ty = int(y) // int(self.tile_h)
        labels: list[str] = []

        for layer_index, layer in enumerate(self._all_layers):
            layer_name = str(getattr(layer, "name", "") or f"layer_{layer_index}")
            layer_visible = self._is_layer_visible(layer, fallback_visible=True)
            runtime_visible = self.layer_visible.get(layer_name, layer_visible)
            if (not include_hidden) and (not runtime_visible):
                continue

            if isinstance(layer, pytmx.TiledTileLayer):
                gid = 0
                try:
                    gid = int(self.tmx_data.get_tile_gid(tx, ty, layer_index) or 0)
                except Exception:
                    try:
                        gid = int(layer.data[ty][tx] or 0)
                    except Exception:
                        gid = 0
                if gid:
                    suffix = "" if runtime_visible else " [hidden]"
                    labels.append(f"tile:{layer_name}{suffix}")
                continue

            if isinstance(layer, pytmx.TiledObjectGroup):
                object_hits = 0
                for obj in layer:
                    if self._object_contains_point(obj, x, y):
                        object_hits += 1
                if object_hits > 0:
                    suffix = "" if runtime_visible else " [hidden]"
                    labels.append(f"obj:{layer_name} x{object_hits}{suffix}")

        # Dynamic collision overlays can be useful for door/chest debugging.
        for dyn_layer, dyn_rects in self.dynamic_layer_rects.items():
            if not self.layer_visible.get(dyn_layer, True):
                continue
            if any(rect.collidepoint(int(x), int(y)) for rect in dyn_rects):
                labels.append(f"dynamic:{dyn_layer}")

        return labels

    def get_collision_sources_for_rect(self, probe_rect: pygame.Rect, limit: int = 6) -> list[str]:
        hits: list[str] = []
        for src in self.collision_sources:
            kind = src.get("kind")
            layer = src.get("layer", "?")
            src_id = src.get("id", "?")
            if kind == "rect":
                rect = src.get("rect")
                if rect is not None and probe_rect.colliderect(rect):
                    hits.append(f"{layer}:{src_id}")
            elif kind == "polygon":
                bbox = src.get("bbox")
                points = src.get("points", [])
                if bbox is not None and probe_rect.colliderect(bbox):
                    if self._polygon_intersects_rect(points, probe_rect):
                        hits.append(f"{layer}:{src_id}")
            if len(hits) >= max(1, int(limit)):
                break
        return hits

    def _build_hazard_rects(self) -> list[pygame.Rect]:
        rects = []
        self.debug_hazard_rects = []
        self.debug_hazard_polygons: list[list[tuple[int, int]]] = []

        for layer in self.tmx_data.objectgroups:
            if getattr(layer, "name", "").strip().lower() != LAYER_HONGOS:
                continue

            for obj in layer:
                if hasattr(obj, 'points') and obj.points:
                    normalized = self._normalize_object_polygon(obj, obj.points)
                    if len(normalized) >= 3:
                        self.debug_hazard_polygons.append([(int(x), int(y)) for x, y in normalized])
                    xs = [p[0] for p in normalized]
                    ys = [p[1] for p in normalized]
                    rx = min(xs)
                    ry = min(ys)
                    rw = max(xs) - rx
                    rh = max(ys) - ry
                else:
                    rx = obj.x
                    ry = obj.y
                    rw = getattr(obj, "width", 0) or self.tile_w
                    rh = getattr(obj, "height", 0) or self.tile_h

                r = pygame.Rect(int(rx), int(ry), int(max(rw, 1)), int(max(rh, 1)))
                rects.append(r)
                self.debug_hazard_rects.append(r)
        return rects

    def _build_layer_rects(self) -> dict:
        layer_rects = {}
        for layer_name in [LAYER_PUERTA_CLOSED, LAYER_COFRE_CLOSED]:
            rects = []
            layer = self._get_tile_layer(layer_name)
            if layer:
                for x, y, gid in layer:
                    if gid:
                        rects.append(pygame.Rect(
                            x * self.tile_w, y * self.tile_h, self.tile_w, self.tile_h
                        ))
            layer_rects[layer_name] = rects
        return layer_rects
        
    def get_dynamic_collisions(self) -> list[pygame.Rect]:
        rects = []
        for layer_name, lst in self.dynamic_layer_rects.items():
            if getattr(self, "layer_visible", {}).get(layer_name, True):
                rects.extend(lst)
        return rects

    def _build_collision_mask(self) -> pygame.mask.Mask:
        mask_surf = pygame.Surface((self.map_width, self.map_height), pygame.SRCALPHA)
        
        # 1. Tiles de collision
        col_layer = self._get_tile_layer(LAYER_COLLISIONS)
        if col_layer is not None:
            for x, y, gid in col_layer:
                if gid:
                    pygame.draw.rect(mask_surf, (255, 255, 255), (x * self.tile_w, y * self.tile_h, self.tile_w, self.tile_h))
                    
        # 2. Objetos y poligonos de la capa de colision activa
        for layer in self.tmx_data.objectgroups:
            if not self._is_collision_layer_name(getattr(layer, "name", "")):
                continue
            for obj in layer:
                if hasattr(obj, 'points') and obj.points and len(obj.points) >= 3:
                    points = self._normalize_object_polygon(obj, obj.points)
                    pygame.draw.polygon(mask_surf, (255, 255, 255), points)
                else:
                    rx = obj.x
                    ry = obj.y
                    rw = getattr(obj, "width", 0) or self.tile_w
                    rh = getattr(obj, "height", 0) or self.tile_h
                    pygame.draw.rect(mask_surf, (255, 255, 255), (rx, ry, rw, rh))
                    
        return pygame.mask.from_surface(mask_surf)

    def get_object_positions(self, object_type: str) -> list[tuple[int, int]]:
        """Devuelve posiciones (px) para objetos por type o name en Tiled."""
        positions = []
        for layer in self.tmx_data.objectgroups:
            for obj in layer:
                if obj.type == object_type or getattr(obj, "name", "") == object_type:
                    positions.append((int(obj.x), int(obj.y)))
        return positions

    def draw_debug_collisions(self, surface: pygame.Surface, offset=(0, 0)):
        """Overlay rojo semitransparente para colisiones (debug). Azul para objetos."""
        overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        ox, oy = offset
        for rect in getattr(self, "debug_tile_col", []):
            debug_rect = rect.move(-ox, -oy)
            pygame.draw.rect(overlay, (255, 0, 0, 80), debug_rect)
        for rect in getattr(self, "debug_obj_col", []):
            debug_rect = rect.move(-ox, -oy)
            pygame.draw.rect(overlay, (0, 0, 255, 120), debug_rect)
        for poly in getattr(self, "debug_obj_polygons", []):
            if len(poly) >= 3:
                pts = [(int(x - ox), int(y - oy)) for x, y in poly]
                pygame.draw.polygon(overlay, (70, 170, 255, 60), pts)
                pygame.draw.polygon(overlay, (120, 210, 255, 170), pts, width=2)
        for rect in getattr(self, "debug_hazard_rects", []):
            debug_rect = rect.move(-ox, -oy)
            pygame.draw.rect(overlay, (255, 128, 0, 120), debug_rect)
        for poly in getattr(self, "debug_hazard_polygons", []):
            if len(poly) >= 3:
                pts = [(int(x - ox), int(y - oy)) for x, y in poly]
                pygame.draw.polygon(overlay, (255, 160, 0, 70), pts)
                pygame.draw.polygon(overlay, (255, 190, 80, 190), pts, width=2)
        surface.blit(overlay, (0, 0))
