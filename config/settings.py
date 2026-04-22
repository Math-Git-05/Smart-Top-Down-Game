# ============================================================
#  config/settings.py  –  Smart Top Down (Encuentra el Mangú)
# ============================================================

# ── Pantalla ─────────────────────────────────────────────────
SCREEN_WIDTH  = 960
SCREEN_HEIGHT = 704
SCREEN_TITLE  = "Asalto Ninja en la Aldea"
FPS           = 60

# ── Mapa / Tiles ─────────────────────────────────────────────
TILE_SIZE     = 32          # px por tile (Tiled exportado en 32x32)
CAMERA_ZOOM   = 2.90        # Zoom de la cámara virtual (estaba en 3.5, lo cual era excesivo)

# ── Jugador ───────────────────────────────────────────────────
PLAYER_SPEED       = 2.3    # px por frame
PLAYER_MAX_HEALTH  = 100
PLAYER_MAX_SHIELD  = 50
PLAYER_MAX_ENERGY  = 100    # limite de energia para uso de proyectiles
PLAYER_ATTACK_DMGM = 20     # daño melee
PLAYER_ATTACK_DMGR = 15     # daño ranged (proyectil)
PLAYER_RANGED_MANA_COST = 12  # costo de mana por disparo ranged (click)
PLAYER_BULLET_SPEED = 4.4

# Pociones activas y limite de spawns por tipo durante una partida.
# Para jugar solo con vida+escudo: ("vida", "escudo")
ENABLED_POTION_TYPES = ("vida", "escudo", "poder")
MAX_POTION_SPAWNS_PER_TYPE = 4

# ── Enemigos ──────────────────────────────────────────────────
ENEMY_A_SPEED        = 0.72  # Ajustado: el perseguidor rapido estaba demasiado agresivo
ENEMY_A_HEALTH       = 80
ENEMY_A_DAMAGE       = 5
ENEMY_A_VISION_RANGE = 200   # px

ENEMY_B_SPEED        = 0     # no se mueve
ENEMY_B_HEALTH       = 60
ENEMY_B_DAMAGE       = 8
ENEMY_B_VISION_RANGE = 300

ENEMY_C_SPEED        = 0.75  # Ajustado: velocidad mas controlada para lectura de combate
ENEMY_C_HEALTH       = 50
ENEMY_C_DAMAGE       = 8
ENEMY_C_VISION_RANGE = 250
ENEMY_C_FLEE_RANGE   = 80    # si el jugador está más cerca que esto, huye
ENEMY_MELEE_RANGE    = 34
ENEMY_CLOSE_RANGE    = 66
ENEMY_BULLET_SPEED   = 3.4
ENEMY_LOW_HP_RATIO   = 0.35

# ── Colores (debug / UI) ──────────────────────────────────────
COLOR_BLACK      = (0,   0,   0)
COLOR_WHITE      = (255, 255, 255)
COLOR_RED        = (220,  50,  50)
COLOR_GREEN      = ( 50, 200,  50)
COLOR_BLUE       = ( 50, 100, 220)
COLOR_YELLOW     = (255, 220,   0)
COLOR_HEALTH_BAR = (220,  50,  50)
COLOR_SHIELD_BAR = ( 50, 150, 220)
COLOR_BG         = ( 30,  30,  30)

# ── Rutas de assets ───────────────────────────────────────────
import os
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR  = os.path.join(BASE_DIR, "assets")
MAPS_DIR    = os.path.join(ASSETS_DIR, "maps")
SPRITES_DIR = os.path.join(ASSETS_DIR, "sprites")
SOUNDS_DIR  = os.path.join(ASSETS_DIR, "sounds")
HONGO_SPRITE = "hongos.png"

# Mapas por nivel (elige el primer archivo existente)
MAP_FILE_LEVEL_1_CANDIDATES = (
    "level1.tmx",
    "MapProd1.tmx",
    "Mapa1.tmx",
    "MapaProd1.tmx",
)

MAP_FILE_LEVEL_2_CANDIDATES = (
    "MapProd2.tmx",
    "Map Proof 2.tmx",
    "MapProof2.tmx",
    "Mapa2.tmx",
)

MAP_FILE_LEVEL_3_CANDIDATES = (
    "MapProd3.tmx",
    "Map Proof 3.tmx",
    "MapProof3.tmx",
    "Mapa3.tmx",
)


def _pick_map_file(candidates: tuple[str, ...]) -> str | None:
    for map_name in candidates:
        candidate = os.path.join(MAPS_DIR, map_name)
        if os.path.exists(candidate):
            return candidate
    return None


MAP_FILE_LEVEL_1 = _pick_map_file(MAP_FILE_LEVEL_1_CANDIDATES) or os.path.join(MAPS_DIR, MAP_FILE_LEVEL_1_CANDIDATES[0])
MAP_FILE_LEVEL_2 = _pick_map_file(MAP_FILE_LEVEL_2_CANDIDATES)
MAP_FILE_LEVEL_3 = _pick_map_file(MAP_FILE_LEVEL_3_CANDIDATES)

# Compat legacy
MAP_FILE = MAP_FILE_LEVEL_1

# --- Capas de Suelo / Base ---
LAYER_PISO_GRASS      = "piso-grass"
LAYER_PISO_DECOR      = "piso-decor"
LAYER_COLLISIONS      = "Coli"
LAYER_WATER           = "agua"

# --- Capas de Estructura ---
LAYER_ESTRUCTURA_BASE  = "estructura-base"
LAYER_ESTRUCTURA_BASE2 = "estructura-base2"
LAYER_ESTRUCTURA_DECOR = "estructura-decor"
LAYER_ESTRUCTURA_ESTATUAS = "estructura-estatuas"
LAYER_ESTRUCTURA_UTILS  = "estructura-utils"

# --- Capas de Objetos e Interactuables ---
LAYER_OBJECTS         = "objects"
LAYER_COFRE_OPEN      = "cofre-open"
LAYER_COFRE_CLOSED    = "cofre-closed"
LAYER_PUERTA_OPEN     = "puerta-open"
LAYER_PUERTA_CLOSED   = "puerta-closed"
LAYER_OBJECTS_OVER    = "objects-over"
LAYER_PLANTAS         = "plantas"
LAYER_HONGOS          = "hongos"
LAYER_ARBUSTOS        = "arbustos"
LAYER_ARBUSTOS2       = "arbustos2"

# Orden real de capas en Tiled (13 capas)
MAP_TILED_LAYER_ORDER = (
    LAYER_PISO_GRASS,
    LAYER_PISO_DECOR,
    LAYER_COLLISIONS,
    LAYER_ESTRUCTURA_BASE,
    LAYER_ESTRUCTURA_BASE2,
    LAYER_ESTRUCTURA_DECOR,
    LAYER_ESTRUCTURA_ESTATUAS,
    LAYER_ESTRUCTURA_UTILS,
    LAYER_OBJECTS,
    LAYER_COFRE_OPEN,
    LAYER_COFRE_CLOSED,
    LAYER_PUERTA_OPEN,
    LAYER_PUERTA_CLOSED,
    LAYER_OBJECTS_OVER,
    LAYER_HONGOS,
    LAYER_PLANTAS,
    LAYER_ARBUSTOS,
    LAYER_ARBUSTOS2,
    LAYER_WATER
    
)

# Capas visuales por debajo/encima del jugador
MAP_RENDER_LAYERS_UNDER_PLAYER = (
    LAYER_WATER,
    LAYER_PISO_GRASS,
    LAYER_PISO_DECOR,
    LAYER_ESTRUCTURA_BASE,
    LAYER_ESTRUCTURA_BASE2,
    LAYER_ESTRUCTURA_DECOR,
    LAYER_ESTRUCTURA_ESTATUAS,
    LAYER_ESTRUCTURA_UTILS,
    LAYER_OBJECTS,
    LAYER_COFRE_OPEN,
    LAYER_COFRE_CLOSED,
    LAYER_PUERTA_OPEN,
    LAYER_PUERTA_CLOSED,
    LAYER_OBJECTS_OVER,
    LAYER_HONGOS,
    LAYER_ARBUSTOS,
    LAYER_ARBUSTOS2,
)
MAP_RENDER_LAYERS_OVER_PLAYER = (
    LAYER_PLANTAS,
)
