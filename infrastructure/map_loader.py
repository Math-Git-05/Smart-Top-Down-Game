# ============================================================
#  infrastructure/map_loader.py - Carga mapas de Tiled (.tmx)
# ============================================================

import pygame
import pytmx
from pytmx.util_pygame import load_pygame

from config.settings import (
    LAYER_COLLISIONS,
    LAYER_HONGOS,
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

        self.layers_under_player = MAP_RENDER_LAYERS_UNDER_PLAYER
        self.layers_over_player = MAP_RENDER_LAYERS_OVER_PLAYER
        self.layer_surfaces = self._build_layer_surfaces()
        
        # Diccionario para permitir ocultar/mostrar capas dinámicamente
        self.layer_visible = {layer: True for layer in self.layer_surfaces}
        
        self.collision_rects = self._build_collision_rects()
        self.hazard_rects = self._build_hazard_rects()
        self.hazard_centers = [rect.center for rect in self.hazard_rects]
        self.dynamic_layer_rects = self._build_layer_rects()
        self.collision_mask = self._build_collision_mask()

    def _get_tile_layer(self, layer_name: str):
        try:
            layer = self.tmx_data.get_layer_by_name(layer_name)
        except (ValueError, KeyError):
            return None
        if isinstance(layer, pytmx.TiledTileLayer):
            return layer
        return None

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
        for layer_name in MAP_TILED_LAYER_ORDER:
            if layer_name == LAYER_COLLISIONS:
                continue
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

        for layer in self.tmx_data.objectgroups:
            if layer.name not in (LAYER_COLLISIONS, "Collisions"):
                continue
            for obj in layer:
                if hasattr(obj, 'points') and obj.points:
                    xs = [p.x for p in obj.points]
                    ys = [p.y for p in obj.points]
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
        return rects

    def _build_hazard_rects(self) -> list[pygame.Rect]:
        rects = []
        self.debug_hazard_rects = []

        for layer in self.tmx_data.objectgroups:
            if getattr(layer, "name", "").strip().lower() != LAYER_HONGOS:
                continue

            for obj in layer:
                if hasattr(obj, 'points') and obj.points:
                    xs = [p.x for p in obj.points]
                    ys = [p.y for p in obj.points]
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
                    
        # 2. Objetos y Poligonos de "Collisions"
        for layer in self.tmx_data.objectgroups:
            if layer.name not in (LAYER_COLLISIONS, "Collisions"):
                continue
            for obj in layer:
                if hasattr(obj, 'points') and obj.points and len(obj.points) >= 3:
                    points = [(p.x, p.y) for p in obj.points]
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
        for rect in getattr(self, "debug_hazard_rects", []):
            debug_rect = rect.move(-ox, -oy)
            pygame.draw.rect(overlay, (255, 128, 0, 120), debug_rect)
        surface.blit(overlay, (0, 0))
