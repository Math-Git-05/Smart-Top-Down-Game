import pygame
import pytmx
from pytmx.util_pygame import load_pygame
import os

pygame.init()
screen = pygame.display.set_mode((960, 704))
tmx_data = load_pygame("c:/Users/Mathe/OneDrive/Documentos/Atraco_Tactico/assets/maps/MapProd1.tmx")

surf = pygame.Surface((tmx_data.width * 32, tmx_data.height * 32), pygame.SRCALPHA)
for layer in tmx_data.visible_layers:
    if isinstance(layer, pytmx.TiledTileLayer):
        for x, y, gid in layer:
            if gid:
                tile = tmx_data.get_tile_image_by_gid(gid)
                if tile:
                    surf.blit(tile, (x*32, y*32))

pygame.image.save(surf, "c:/Users/Mathe/OneDrive/Documentos/Atraco_Tactico/test_render_all.png")
print("Saved to test_render_all.png")
