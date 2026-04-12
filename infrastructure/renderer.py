# ============================================================
#  infrastructure/renderer.py - Camara y renderizado
# ============================================================

import os
import pygame
from config.settings import SCREEN_WIDTH, SCREEN_HEIGHT, CAMERA_ZOOM, SPRITES_DIR, TILE_SIZE, HONGO_SPRITE


class Camera:
    """
    Camara centrada en el jugador.
    Convierte coordenadas del mundo a coordenadas de pantalla.
    """

    def __init__(self, map_width: int, map_height: int):
        self.offset_x = 0
        self.offset_y = 0
        self.map_width = map_width
        self.map_height = map_height
        
        self.view_w = int(SCREEN_WIDTH / CAMERA_ZOOM)
        self.view_h = int(SCREEN_HEIGHT / CAMERA_ZOOM)

    def update(self, target: pygame.sprite.Sprite):
        """Centra la camara en el target (jugador)."""
        cx = target.rect.centerx - self.view_w // 2
        cy = target.rect.centery - self.view_h // 2

        self.offset_x = max(0, min(cx, self.map_width - self.view_w))
        self.offset_y = max(0, min(cy, self.map_height - self.view_h))

    def apply(self, rect: pygame.Rect) -> pygame.Rect:
        """Devuelve el rect ajustado al offset de la camara."""
        return rect.move(-self.offset_x, -self.offset_y)

    def apply_pos(self, x: int, y: int) -> tuple[int, int]:
        return x - self.offset_x, y - self.offset_y

    @property
    def offset(self) -> tuple[int, int]:
        return self.offset_x, self.offset_y


class Renderer:
    """
    Centraliza el dibujado del frame.
    Orden sugerido: mapa_under -> sprites -> mapa_over -> HUD
    """

    def __init__(self, screen: pygame.Surface, camera: Camera):
        self.real_screen = screen
        self.camera = camera
        
        if CAMERA_ZOOM != 1.0:
            self.screen = pygame.Surface((camera.view_w, camera.view_h))
        else:
            self.screen = screen
            
        self.icon_health = self._load_and_tint_icon("corazon.png", (220, 50, 50))
        self.icon_shield = self._load_and_tint_icon("escudo.png", (50, 150, 220))
        self.icon_energy = self._load_and_tint_icon("poder.png", (220, 180, 50))
        self.hazard_sprite = self._load_sprite(HONGO_SPRITE, (TILE_SIZE, TILE_SIZE))

    def _load_and_tint_icon(self, filename, color, size=(16, 16)):
        path = os.path.join(SPRITES_DIR, filename)
        if os.path.exists(path):
            try:
                img = pygame.image.load(path).convert_alpha()
                img = pygame.transform.smoothscale(img, size)
                # Tint the image dynamically preserving alpha channel
                tint = pygame.Surface(size, pygame.SRCALPHA)
                tint.fill((*color, 255))
                img.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                return img
            except Exception:
                pass
        return None

    def _load_sprite(self, filename, size=(32, 32)):
        path = os.path.join(SPRITES_DIR, filename)
        if os.path.exists(path):
            try:
                img = pygame.image.load(path).convert_alpha()
                return pygame.transform.smoothscale(img, size)
            except Exception:
                pass
        return None

    def draw_hazards(self, map_loader):
        if not self.hazard_sprite:
            return
        for rect in getattr(map_loader, "hazard_rects", []):
            pos = self.camera.apply_pos(*rect.center)
            sprite_rect = self.hazard_sprite.get_rect(center=pos)
            self.screen.blit(self.hazard_sprite, sprite_rect)
            
    def present(self):
        if CAMERA_ZOOM != 1.0:
            scaled = pygame.transform.scale(self.screen, self.real_screen.get_size())
            self.real_screen.blit(scaled, (0, 0))

    def draw_map_layers(self, map_loader, layer_names):
        """Dibuja un conjunto de capas del mapa con offset de camara."""
        map_loader.draw_layers(self.screen, layer_names, self.camera.offset)

    def draw_sprites(self, sprite_group: pygame.sprite.Group):
        """Dibuja sprites ordenados por rect.bottom para profundidad Y."""
        for sprite in sorted(sprite_group, key=lambda s: s.rect.bottom):
            screen_rect = self.camera.apply(sprite.rect)
            self.screen.blit(sprite.image, screen_rect)

    def draw_hud(self, player):
        """Barra de vida, escudo y energia del jugador (esquina superior izquierda)."""
        self._draw_bar(10, 10, player.health, player.max_health, (220, 50, 50), self.icon_health)
        self._draw_bar(10, 30, player.shield, player.max_shield, (50, 150, 220), self.icon_shield)
        self._draw_bar(10, 50, player.energy, player.max_energy, (220, 180, 50), self.icon_energy)

    def _draw_bar(self, x, y, value, max_value, color, icon):
        BAR_W, BAR_H = 140, 14
        
        if icon:
            self.real_screen.blit(icon, (x, y - (icon.get_height() - BAR_H)//2))
            x += icon.get_width() + 6
            
        ratio = max(0, value / max_value)
        pygame.draw.rect(self.real_screen, (60, 60, 60), (x, y, BAR_W, BAR_H))
        pygame.draw.rect(self.real_screen, color, (x, y, int(BAR_W * ratio), BAR_H))
        pygame.draw.rect(self.real_screen, (200, 200, 200), (x, y, BAR_W, BAR_H), 1)

    def draw_debug_collisions(self, map_loader):
        map_loader.draw_debug_collisions(self.screen, self.camera.offset)
