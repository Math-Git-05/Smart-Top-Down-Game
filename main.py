# ============================================================
#  main.py - Entry point | Smart Top Down
#           "Encuentra el Mangu Legendario"
# ============================================================

import os
import sys

import pygame

from config.settings import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    SCREEN_TITLE,
    FPS,
    MAP_FILE,
    SPRITES_DIR,
    COLOR_BG,
    LAYER_PUERTA_CLOSED,
    LAYER_PUERTA_OPEN,
    LAYER_COFRE_CLOSED,
    LAYER_COFRE_OPEN,
)
from infrastructure.map_loader import MapLoader
from infrastructure.renderer import Camera, Renderer
from core.player import Player
from core.item_manager import ItemManager


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


def main() -> str:
    pygame.init()
    pygame.mixer.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(SCREEN_TITLE)
    clock = pygame.time.Clock()

    print(f"[main] Cargando mapa: {MAP_FILE}")
    try:
        game_map = MapLoader(MAP_FILE)

        # Puerta: abierta al iniciar intro
        if LAYER_PUERTA_CLOSED in game_map.layer_visible:
            game_map.layer_visible[LAYER_PUERTA_CLOSED] = False
        if LAYER_PUERTA_OPEN in game_map.layer_visible:
            game_map.layer_visible[LAYER_PUERTA_OPEN] = True

        # Cofre: cerrado visible, abierto invisible
        if LAYER_COFRE_CLOSED in game_map.layer_visible:
            game_map.layer_visible[LAYER_COFRE_CLOSED] = True
        if LAYER_COFRE_OPEN in game_map.layer_visible:
            game_map.layer_visible[LAYER_COFRE_OPEN] = False
    except Exception as e:
        print(f"[ERROR] No se pudo cargar el mapa: {e}")
        print("  Asegurate de que assets/maps/level1.tmx existe.")
        print("  Mientras tanto se usara un mapa en negro de placeholder.")
        game_map = None

    map_w = game_map.map_width if game_map else SCREEN_WIDTH * 2
    map_h = game_map.map_height if game_map else SCREEN_HEIGHT * 2

    all_sprites = pygame.sprite.Group()
    bullet_group = pygame.sprite.Group()
    enemy_group = pygame.sprite.Group()

    collision_rects = game_map.collision_rects if game_map else []
    collision_mask = game_map.collision_mask if game_map else None

    # Entrada y salida por la misma escalera
    spawn_x, spawn_y = 24 * 32, 26 * 32
    intro_target_y = 21 * 32
    exit_axis_x = 24.5 * 32
    exit_start_y = intro_target_y

    intro_active = True
    intro_start_time = pygame.time.get_ticks()
    intro_fade_duration = 2000

    player_sprite = os.path.join(SPRITES_DIR, "player", "playerSP.png")
    player = Player(
        x=spawn_x,
        y=spawn_y,
        groups=(all_sprites,),
        collision_rects=collision_rects,
        bullet_group=bullet_group,
        sprite_path=player_sprite,
        collision_mask=collision_mask,
    )

    camera = Camera(map_w, map_h)
    renderer = Renderer(screen, camera)
    item_manager = ItemManager(game_map) if game_map else None

    door_trigger_rect = _build_layer_trigger_rect(game_map, LAYER_PUERTA_CLOSED, inflate=26)

    # Estado de fin de nivel
    exit_sequence_active = False
    exit_phase = "none"  # none, walk_down, fade_out, end_screen
    exit_walk_speed = 1.0
    exit_fade_start_ms = 0
    exit_fade_duration_ms = 1400
    final_overlay_alpha = 0

    end_title_font = pygame.font.SysFont("arial", 38, bold=True)
    end_text_font = pygame.font.SysFont("arial", 24)

    debug_collisions = False
    death_screen = False
    final_action = "quit"

    print("[main] Game loop iniciado. Controles:")
    print("  WASD / Flechas -> mover")
    print("  Z              -> ataque melee")
    print("  X              -> proyectil")
    print("  Espacio        -> defender")
    print("  F1             -> toggle debug colisiones")
    print("  ESC            -> salir")

    running = True
    while running:
        now_ms = pygame.time.get_ticks()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                final_action = "quit"
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                    final_action = "quit"
                elif event.key == pygame.K_F1:
                    debug_collisions = not debug_collisions
                    print(f"[debug] colisiones: {debug_collisions}")
                elif (exit_phase == "end_screen" or death_screen) and event.key == pygame.K_r:
                    running = False
                    final_action = "restart"

        # Activar secuencia de salida al volver a la puerta con salami
        if (
            not intro_active
            and not exit_sequence_active
            and door_trigger_rect is not None
            and getattr(player, "has_salami", False)
            and player.hitbox.colliderect(door_trigger_rect)
        ):
            exit_sequence_active = True
            exit_phase = "walk_down"
            # Fuerza el mismo path del intro (mismo X y punto de arranque en Y).
            player._pos.x = exit_axis_x
            player._pos.y = exit_start_y
            player.hitbox.centerx = int(exit_axis_x)
            player.hitbox.centery = int(exit_start_y)
            player.rect.center = player.hitbox.center
            print("[main] Salami obtenido. Iniciando salida por puerta.")
            if game_map:
                if LAYER_PUERTA_OPEN in game_map.layer_visible:
                    game_map.layer_visible[LAYER_PUERTA_OPEN] = True
                if LAYER_PUERTA_CLOSED in game_map.layer_visible:
                    game_map.layer_visible[LAYER_PUERTA_CLOSED] = False

        # Logica principal de movimiento
        if intro_active:
            player.state = "walk"
            player.direction = "up"
            player._pos.y -= 1
            player.hitbox.centery = int(player._pos.y)
            player.rect.center = player.hitbox.center

            if player._pos.y <= intro_target_y:
                player._pos.y = intro_target_y
                player.hitbox.centery = intro_target_y
                player.rect.center = player.hitbox.center
                intro_active = False
                player.state = "idle"
                if game_map:
                    if LAYER_PUERTA_OPEN in game_map.layer_visible:
                        game_map.layer_visible[LAYER_PUERTA_OPEN] = False
                    if LAYER_PUERTA_CLOSED in game_map.layer_visible:
                        game_map.layer_visible[LAYER_PUERTA_CLOSED] = True

            player._update_animation()
        elif exit_sequence_active:
            if exit_phase == "walk_down":
                player.state = "walk"
                player.direction = "down"
                player._pos.x = exit_axis_x
                player.hitbox.centerx = int(exit_axis_x)
                player._pos.y += exit_walk_speed
                player.hitbox.centery = int(player._pos.y)
                player.rect.center = player.hitbox.center
                player._update_animation()

                if player._pos.y >= spawn_y:
                    player._pos.y = spawn_y
                    player.hitbox.centery = spawn_y
                    player.rect.center = player.hitbox.center
                    player.state = "idle"
                    exit_phase = "fade_out"
                    exit_fade_start_ms = now_ms
                    final_overlay_alpha = 0

            elif exit_phase == "fade_out":
                player.state = "idle"
                player._update_animation()
                elapsed = now_ms - exit_fade_start_ms
                final_overlay_alpha = min(255, int((elapsed / max(1, exit_fade_duration_ms)) * 255))
                if final_overlay_alpha >= 255:
                    exit_phase = "end_screen"
                    final_overlay_alpha = 255
            else:
                player.state = "idle"
                player._update_animation()
        else:
            keys = pygame.key.get_pressed()
            player.update(keys, enemies=list(enemy_group), game_map=game_map)
            if not player.alive:
                death_screen = True

        if item_manager and not exit_sequence_active and not death_screen:
            item_manager.update(player, intro_active=intro_active)

        bullet_group.update()
        camera.update(player)

        renderer.screen.fill(COLOR_BG)

        if game_map:
            renderer.draw_map_layers(game_map, game_map.layers_under_player)
            renderer.draw_hazards(game_map)
        else:
            pygame.draw.rect(
                renderer.screen,
                (40, 80, 40),
                (0, 0, renderer.camera.view_w, renderer.camera.view_h),
            )

        if item_manager:
            item_manager.draw_world(renderer.screen, camera)

        renderer.draw_sprites(all_sprites)

        for bullet in bullet_group:
            screen_rect = camera.apply(bullet.rect)
            renderer.screen.blit(bullet.image, screen_rect)

        if game_map:
            renderer.draw_map_layers(game_map, game_map.layers_over_player)

        if item_manager:
            item_manager.draw_overlay(renderer.screen, camera, player)

        if debug_collisions and game_map:
            renderer.draw_debug_collisions(game_map)

        renderer.present()
        renderer.draw_hud(player)

        # Fade in inicial
        if intro_active:
            elapsed = now_ms - intro_start_time
            alpha = max(0, 255 - int((elapsed / intro_fade_duration) * 255))
            if alpha > 0:
                fade_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
                fade_surface.fill((0, 0, 0))
                fade_surface.set_alpha(alpha)
                screen.blit(fade_surface, (0, 0))

        # Fade out final
        if exit_phase in ("fade_out", "end_screen"):
            fade_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_surface.fill((0, 0, 0))
            fade_surface.set_alpha(final_overlay_alpha)
            screen.blit(fade_surface, (0, 0))

        if exit_phase == "end_screen":
            title = end_title_font.render("Mision Completada", True, (245, 245, 245))
            line1 = end_text_font.render("Presione R para reiniciar", True, (225, 225, 225))
            line2 = end_text_font.render("o ESC para salir", True, (225, 225, 225))
            screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30)))
            screen.blit(line1, line1.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20)))
            screen.blit(line2, line2.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 55)))

        if death_screen:
            fade_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            fade_surface.fill((0, 0, 0))
            fade_surface.set_alpha(220)
            screen.blit(fade_surface, (0, 0))
            title = end_title_font.render("Has muerto", True, (220, 80, 80))
            line1 = end_text_font.render("Presione R para reiniciar", True, (225, 225, 225))
            line2 = end_text_font.render("o ESC para salir", True, (225, 225, 225))
            screen.blit(title, title.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 30)))
            screen.blit(line1, line1.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 20)))
            screen.blit(line2, line2.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 55)))

        if debug_collisions:
            font = pygame.font.SysFont("monospace", 14)
            info = [
                f"FPS: {clock.get_fps():.0f}",
                f"Player: ({player.rect.x}, {player.rect.y})",
                f"Dir: {player.direction}",
                f"Defending: {player.is_defending}",
                f"HP: {player.health} | Shield: {player.shield:.0f}",
                f"Frags: {getattr(player, 'key_fragments', 0)}/3 | Key: {getattr(player, 'has_key', False)}",
                f"Salami: {getattr(player, 'has_salami', False)}",
                f"Exit phase: {exit_phase}",
            ]
            for i, text in enumerate(info):
                surf = font.render(text, True, (255, 255, 0))
                screen.blit(surf, (10, SCREEN_HEIGHT - 138 + i * 16))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    return final_action


if __name__ == "__main__":
    next_action = "restart"
    while next_action == "restart":
        next_action = main()
    sys.exit()
