from __future__ import annotations

from dataclasses import dataclass
import math

import pygame

from config.settings import SCREEN_HEIGHT, SCREEN_WIDTH

ENEMY_SCENARIO_OPTIONS: list[tuple[str, str, str]] = [
    ("a_vs_1_agent", "i. Un enemigo tipo A vs 1 agente", "A vs 1"),
    ("b_vs_1_agent", "ii. Un enemigo tipo B vs 1 agente", "B vs 1"),
    ("c_vs_1_agent", "iii. Un enemigo tipo C vs 1 agente", "C vs 1"),
    ("human_vs_1_agent", "iv. Un jugador humano vs 1 agente", "Humano vs 1"),
    ("many_a_vs_1_agent", "v. Varios enemigos tipo A vs 1 agente", "Muchos A"),
    ("many_b_vs_1_agent", "vi. Varios enemigos tipo B vs 1 agente", "Muchos B"),
    ("many_c_vs_1_agent", "vii. Varios enemigos tipo C vs 1 agente", "Muchos C"),
    ("mixed_vs_1_agent", "viii. Varios de todos vs 1 agente", "Mixto vs 1"),
    ("mixed_vs_many_agents", "ix. Varios de todos vs varios agentes", "Mixto vs varios"),
    ("human_vs_many_agents", "x. Un jugador humano vs varios agentes", "Humano vs varios"),
]
ENEMY_SCENARIO_KEYS = [item[0] for item in ENEMY_SCENARIO_OPTIONS]


def enemy_scenario_label(code: str, short: bool = False) -> str:
    for key, long_label, short_label in ENEMY_SCENARIO_OPTIONS:
        if code == key:
            return short_label if short else long_label
    fallback = ENEMY_SCENARIO_OPTIONS[7]  # mixed_vs_1_agent
    return fallback[2] if short else fallback[1]


@dataclass(slots=True)
class AgentMenuConfig:
    sandbox_enemy_count: int = 3
    enemy_scenario: str = "mixed_vs_1_agent"
    ally_agents_enabled: bool = True
    ally_agents_count: int = 2  # cantidad de aliados visuales/de apoyo (excluye al heroe)
    training_level: str = "sandbox"  # level_1 | level_2 | level_3 | sandbox
    benchmark_runs: int = 4
    population_size: int = 8
    generations: int = 4
    crossover_mode: str = "uniform"  # uniform | single_point | blend
    selection_mode: str = "tournament"  # tournament | roulette | rank
    mutation_rate: float = 0.18
    mutation_scale: float = 0.30
    weight_aggression: float = 1.0
    weight_survival: float = 1.0
    weight_objective: float = 1.2
    weight_pathing: float = 1.0

    def copy(self) -> "AgentMenuConfig":
        return AgentMenuConfig(
            sandbox_enemy_count=int(self.sandbox_enemy_count),
            enemy_scenario=str(self.enemy_scenario),
            ally_agents_enabled=bool(self.ally_agents_enabled),
            ally_agents_count=int(self.ally_agents_count),
            training_level=str(self.training_level),
            benchmark_runs=int(self.benchmark_runs),
            population_size=int(self.population_size),
            generations=int(self.generations),
            crossover_mode=str(self.crossover_mode),
            selection_mode=str(self.selection_mode),
            mutation_rate=float(self.mutation_rate),
            mutation_scale=float(self.mutation_scale),
            weight_aggression=float(self.weight_aggression),
            weight_survival=float(self.weight_survival),
            weight_objective=float(self.weight_objective),
            weight_pathing=float(self.weight_pathing),
        )


@dataclass(slots=True)
class MenuResult:
    action: str
    config: AgentMenuConfig


def _draw_background(surface: pygame.Surface, t: int):
    surface.fill((20, 22, 18))

    for i in range(28):
        px = int((i * 73 + (t * (0.36 + i * 0.014))) % (SCREEN_WIDTH + 160)) - 80
        py = int((SCREEN_HEIGHT * 0.25) + math.sin((t * 0.018) + i * 0.41) * 150)
        radius = 16 + (i % 4) * 5
        alpha = 16 + (i % 3) * 9
        blob = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(blob, (72, 108, 66, alpha), (radius, radius), radius)
        surface.blit(blob, (px, py))

    band = pygame.Surface((SCREEN_WIDTH, 230), pygame.SRCALPHA)
    pygame.draw.rect(band, (40, 54, 36, 188), band.get_rect(), border_radius=16)
    surface.blit(band, (0, 84))


def _draw_card(surface: pygame.Surface, rect: pygame.Rect, fill, border=(140, 168, 126), border_width: int = 2):
    pygame.draw.rect(surface, fill, rect, border_radius=14)
    pygame.draw.rect(surface, border, rect, width=border_width, border_radius=14)


def _render_label(font: pygame.font.Font, text: str, color=(240, 240, 240)) -> pygame.Surface:
    return font.render(text, True, color)


def _cycle_value(options: list[str], current: str, direction: int) -> str:
    idx = options.index(current) if current in options else 0
    idx = (idx + direction) % len(options)
    return options[idx]


def _row_adjust_enabled(config: AgentMenuConfig, row_key: str) -> bool:
    if row_key in ("train_agent", "run_benchmark", "backoffice_demo", "back"):
        return False
    if row_key == "sandbox_enemy_count" and config.training_level != "sandbox":
        return False
    if row_key == "ally_agents_enabled" and config.enemy_scenario not in ("mixed_vs_many_agents", "human_vs_many_agents"):
        return False
    if row_key == "ally_agents_count":
        if config.enemy_scenario not in ("mixed_vs_many_agents", "human_vs_many_agents"):
            return False
        if not config.ally_agents_enabled:
            return False
    return True


def run_backoffice_menu(screen: pygame.Surface, clock: pygame.time.Clock, config: AgentMenuConfig) -> MenuResult:
    title_font = pygame.font.SysFont("verdana", 40, bold=True)
    row_font = pygame.font.SysFont("verdana", 22, bold=True)
    small_font = pygame.font.SysFont("verdana", 17)

    all_rows = [
        ("training_level", "Nivel entrenamiento"),
        ("sandbox_enemy_count", "Enemigos sandbox"),
        ("enemy_scenario", "Escenario combate"),
        ("ally_agents_enabled", "Aliados soporte"),
        ("ally_agents_count", "Cantidad aliados"),
        ("population_size", "Poblacion"),
        ("generations", "Generaciones"),
        ("crossover_mode", "Cruce"),
        ("selection_mode", "Seleccion"),
        ("mutation_rate", "Mutacion"),
        ("mutation_scale", "Escala mutacion"),
        ("weight_aggression", "Peso agresion"),
        ("weight_survival", "Peso supervivencia"),
        ("weight_objective", "Peso objetivo"),
        ("weight_pathing", "Peso stalking"),
        ("benchmark_runs", "Corridas benchmark"),
        ("train_agent", "Entrenar agente"),
        ("run_benchmark", "Correr benchmark"),
        ("backoffice_demo", "Demo agente en backoffice"),
        ("back", "Volver"),
    ]
    pages = [
        ("Basico", all_rows[:9]),
        ("Pesos", all_rows[9:15]),
        ("Acciones", all_rows[15:]),
    ]

    page_idx = 0
    selected_by_page = [0 for _ in pages]
    blink_until = 0
    t = 0

    while True:
        now = pygame.time.get_ticks()
        rows = pages[page_idx][1]
        selected = selected_by_page[page_idx]
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return MenuResult("quit", config.copy())
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return MenuResult("back", config.copy())
                if event.key in (pygame.K_TAB, pygame.K_q, pygame.K_e):
                    direction = 1
                    if event.key == pygame.K_q:
                        direction = -1
                    page_idx = (page_idx + direction) % len(pages)
                    rows = pages[page_idx][1]
                    selected = selected_by_page[page_idx] % max(1, len(rows))
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(rows)
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(rows)
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    if _row_adjust_enabled(config, rows[selected][0]):
                        _adjust_backoffice_value(config, rows[selected][0], -1)
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    if _row_adjust_enabled(config, rows[selected][0]):
                        _adjust_backoffice_value(config, rows[selected][0], +1)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    action = rows[selected][0]
                    if action in ("train_agent", "run_benchmark", "backoffice_demo", "back"):
                        return MenuResult(action, config.copy())
                    blink_until = now + 260
                selected_by_page[page_idx] = selected

        t += 1
        _draw_background(screen, t)

        main_rect = pygame.Rect(44, 62, SCREEN_WIDTH - 88, SCREEN_HEIGHT - 124)
        _draw_card(screen, main_rect, (26, 35, 28), border=(164, 196, 142), border_width=3)

        title = _render_label(title_font, "BACKOFFICE IA", (230, 246, 220))
        screen.blit(title, (main_rect.x + 22, main_rect.y + 14))

        subtitle = _render_label(
            small_font,
            "TAB/Q/E pagina. Ajusta seleccion, cruces, mutacion y pesos.",
            (178, 206, 166),
        )
        screen.blit(subtitle, (main_rect.x + 22, main_rect.y + 62))

        tab_left = _render_label(small_font, "<", (210, 236, 192))
        tab_right = _render_label(small_font, ">", (210, 236, 192))
        page_label = _render_label(small_font, f"Pagina {page_idx + 1}/{len(pages)} - {pages[page_idx][0]}", (226, 238, 218))
        screen.blit(tab_left, (main_rect.right - 254, main_rect.y + 63))
        screen.blit(page_label, (main_rect.right - 236, main_rect.y + 63))
        screen.blit(tab_right, (main_rect.right - 22, main_rect.y + 63))

        start_y = main_rect.y + 96
        for idx, (key, label) in enumerate(rows):
            row_rect = pygame.Rect(main_rect.x + 18, start_y + idx * 46, main_rect.width - 36, 38)
            is_selected = idx == selected
            can_adjust = _row_adjust_enabled(config, key)
            bg = (52, 72, 50) if is_selected else (33, 45, 34)
            border = (208, 236, 188) if is_selected else (90, 120, 84)
            if not can_adjust and key not in ("train_agent", "run_benchmark", "backoffice_demo", "back"):
                bg = (30, 36, 31) if not is_selected else (42, 50, 43)
                border = (92, 106, 90)
            _draw_card(screen, row_rect, bg, border=border, border_width=2)

            left_color = (244, 248, 242) if is_selected else (220, 230, 216)
            if not can_adjust and key not in ("train_agent", "run_benchmark", "backoffice_demo", "back"):
                left_color = (166, 174, 164)
            left = _render_label(row_font, label, left_color)
            screen.blit(left, (row_rect.x + 10, row_rect.y + 6))

            value_text = _value_text_for_row(config, key)
            if value_text:
                right_color = (255, 224, 138) if is_selected else (208, 220, 210)
                if not can_adjust and key not in ("train_agent", "run_benchmark", "backoffice_demo", "back"):
                    right_color = (144, 156, 146)
                right = _render_label(row_font, value_text, right_color)
                screen.blit(right, (row_rect.right - right.get_width() - 10, row_rect.y + 6))

        help_text = "ENTER ejecutar | IZQ/DER ajustar | TAB/Q/E pagina | ESC volver"
        help_surface = _render_label(small_font, help_text, (166, 190, 160))
        screen.blit(help_surface, (main_rect.x + 18, main_rect.bottom - 34))

        if blink_until > now:
            note = _render_label(small_font, "Valor actualizado", (255, 214, 118))
            screen.blit(note, (main_rect.right - note.get_width() - 20, main_rect.bottom - 34))

        pygame.display.flip()
        clock.tick(60)


def _value_text_for_row(config: AgentMenuConfig, row_key: str) -> str:
    if row_key == "training_level":
        name = {
            "level_1": "Nivel 1",
            "level_2": "Nivel 2",
            "level_3": "Nivel 3",
            "sandbox": "Sandbox",
        }
        return name.get(config.training_level, config.training_level)
    if row_key == "population_size":
        return str(config.population_size)
    if row_key == "sandbox_enemy_count":
        if config.training_level != "sandbox":
            return "solo sandbox"
        return str(config.sandbox_enemy_count)
    if row_key == "enemy_scenario":
        return enemy_scenario_label(config.enemy_scenario, short=True)
    if row_key == "ally_agents_enabled":
        return "SI" if config.ally_agents_enabled else "NO"
    if row_key == "ally_agents_count":
        return str(max(0, int(config.ally_agents_count)))
    if row_key == "generations":
        return str(config.generations)
    if row_key == "crossover_mode":
        labels = {
            "uniform": "Uniforme",
            "single_point": "1 punto",
            "blend": "Blend",
        }
        return labels.get(config.crossover_mode, config.crossover_mode)
    if row_key == "selection_mode":
        labels = {
            "tournament": "Torneo",
            "roulette": "Ruleta",
            "rank": "Ranking",
        }
        return labels.get(config.selection_mode, config.selection_mode)
    if row_key == "mutation_rate":
        return f"{config.mutation_rate:.2f}"
    if row_key == "mutation_scale":
        return f"{config.mutation_scale:.2f}"
    if row_key == "weight_aggression":
        return f"{config.weight_aggression:.2f}"
    if row_key == "weight_survival":
        return f"{config.weight_survival:.2f}"
    if row_key == "weight_objective":
        return f"{config.weight_objective:.2f}"
    if row_key == "weight_pathing":
        return f"{config.weight_pathing:.2f}"
    if row_key == "benchmark_runs":
        return str(config.benchmark_runs)
    return ""


def _adjust_backoffice_value(config: AgentMenuConfig, row_key: str, direction: int):
    if row_key == "training_level":
        config.training_level = _cycle_value(["level_1", "level_2", "level_3", "sandbox"], config.training_level, direction)
    elif row_key == "sandbox_enemy_count":
        if config.training_level == "sandbox":
            config.sandbox_enemy_count = max(1, min(50, config.sandbox_enemy_count + direction))
    elif row_key == "enemy_scenario":
        config.enemy_scenario = _cycle_value(ENEMY_SCENARIO_KEYS, config.enemy_scenario, direction)
    elif row_key == "ally_agents_enabled":
        config.ally_agents_enabled = not bool(config.ally_agents_enabled)
    elif row_key == "ally_agents_count":
        config.ally_agents_count = max(0, min(8, int(config.ally_agents_count) + direction))
    elif row_key == "population_size":
        config.population_size = max(2, min(48, config.population_size + direction))
    elif row_key == "generations":
        config.generations = max(1, min(40, config.generations + direction))
    elif row_key == "crossover_mode":
        config.crossover_mode = _cycle_value(["uniform", "single_point", "blend"], config.crossover_mode, direction)
    elif row_key == "selection_mode":
        config.selection_mode = _cycle_value(["tournament", "roulette", "rank"], config.selection_mode, direction)
    elif row_key == "mutation_rate":
        config.mutation_rate = max(0.01, min(0.90, config.mutation_rate + (0.01 * direction)))
    elif row_key == "mutation_scale":
        config.mutation_scale = max(0.01, min(1.20, config.mutation_scale + (0.02 * direction)))
    elif row_key == "weight_aggression":
        config.weight_aggression = max(-1.5, min(3.0, config.weight_aggression + (0.05 * direction)))
    elif row_key == "weight_survival":
        config.weight_survival = max(-1.5, min(3.0, config.weight_survival + (0.05 * direction)))
    elif row_key == "weight_objective":
        config.weight_objective = max(-1.5, min(3.0, config.weight_objective + (0.05 * direction)))
    elif row_key == "weight_pathing":
        config.weight_pathing = max(-1.5, min(3.0, config.weight_pathing + (0.05 * direction)))
    elif row_key == "benchmark_runs":
        config.benchmark_runs = max(1, min(40, config.benchmark_runs + direction))


def run_main_menu(
    screen: pygame.Surface,
    clock: pygame.time.Clock,
    config: AgentMenuConfig | None = None,
) -> MenuResult:
    cfg = config.copy() if config is not None else AgentMenuConfig()

    title_font = pygame.font.SysFont("verdana", 54, bold=True)
    subtitle_font = pygame.font.SysFont("verdana", 22, bold=True)
    option_font = pygame.font.SysFont("verdana", 26, bold=True)
    small_font = pygame.font.SysFont("verdana", 17)

    pages = [
        (
            "Partidas",
            [
                ("play_level_1", "Jugar Nivel 1", "Tutorial disponible"),
                ("level_2_placeholder", "Jugar Nivel 2", "Mapa 2 (usa selector de escenario)"),
                ("level_3_placeholder", "Jugar Nivel 3", "Mapa 3 (usa selector de escenario)"),
                ("play_sandbox", "Sandbox", "Prueba libre con enemigos configurables"),
            ],
        ),
        (
            "Demos",
            [
                ("play_agent_level_1", "Demo Agente Nivel 1", "Agente autonomo en mapa principal"),
                ("play_agent_selected", "Demo Agente (Nivel BO)", "Usa el nivel seleccionado en Backoffice"),
                ("play_agent_sandbox", "Demo Agente Sandbox", "Agente autonomo en arena de prueba"),
            ],
        ),
        (
            "IA y Config",
            [
                ("scenario_select", "Escenario por Nivel", "Selecciona el enfrentamiento i-x"),
                ("ally_toggle_main", "Aliados de apoyo", "Activa o desactiva aliados en escenarios mixtos"),
                ("ally_count_main", "Cantidad aliados", "Define cuantos aliados de apoyo aparecen (0-8)"),
                ("open_backoffice", "Backoffice IA", "Entrenamiento, cruces, seleccion y benchmark"),
                ("quit", "Salir", "Cerrar juego"),
            ],
        ),
    ]

    page_idx = 0
    selected_by_page = [0 for _ in pages]
    t = 0

    while True:
        rows = pages[page_idx][1]
        selected = selected_by_page[page_idx] % max(1, len(rows))
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return MenuResult("quit", cfg.copy())
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return MenuResult("quit", cfg.copy())
                if event.key in (pygame.K_TAB, pygame.K_q, pygame.K_e):
                    direction = 1
                    if event.key == pygame.K_q:
                        direction = -1
                    page_idx = (page_idx + direction) % len(pages)
                    rows = pages[page_idx][1]
                    selected = selected_by_page[page_idx] % max(1, len(rows))
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(rows)
                if event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(rows)
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    current_action = rows[selected][0]
                    if current_action in ("play_sandbox", "play_agent_sandbox"):
                        cfg.sandbox_enemy_count = max(1, cfg.sandbox_enemy_count - 1)
                    elif current_action == "scenario_select":
                        cfg.enemy_scenario = _cycle_value(ENEMY_SCENARIO_KEYS, cfg.enemy_scenario, -1)
                    elif current_action == "ally_toggle_main":
                        cfg.ally_agents_enabled = not bool(cfg.ally_agents_enabled)
                    elif current_action == "ally_count_main":
                        cfg.ally_agents_count = max(0, min(8, int(cfg.ally_agents_count) - 1))
                    elif current_action == "play_agent_selected":
                        cfg.training_level = _cycle_value(["level_1", "level_2", "level_3", "sandbox"], cfg.training_level, -1)
                if event.key in (pygame.K_RIGHT, pygame.K_d):
                    current_action = rows[selected][0]
                    if current_action in ("play_sandbox", "play_agent_sandbox"):
                        cfg.sandbox_enemy_count = min(50, cfg.sandbox_enemy_count + 1)
                    elif current_action == "scenario_select":
                        cfg.enemy_scenario = _cycle_value(ENEMY_SCENARIO_KEYS, cfg.enemy_scenario, +1)
                    elif current_action == "ally_toggle_main":
                        cfg.ally_agents_enabled = not bool(cfg.ally_agents_enabled)
                    elif current_action == "ally_count_main":
                        cfg.ally_agents_count = max(0, min(8, int(cfg.ally_agents_count) + 1))
                    elif current_action == "play_agent_selected":
                        cfg.training_level = _cycle_value(["level_1", "level_2", "level_3", "sandbox"], cfg.training_level, +1)
                if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    action = rows[selected][0]
                    if action == "open_backoffice":
                        result = run_backoffice_menu(screen, clock, cfg)
                        cfg = result.config.copy()
                        if result.action in ("quit", "train_agent", "run_benchmark", "backoffice_demo"):
                            return MenuResult(result.action, cfg.copy())
                        continue
                    if action == "scenario_select":
                        cfg.enemy_scenario = _cycle_value(ENEMY_SCENARIO_KEYS, cfg.enemy_scenario, +1)
                        continue
                    if action == "ally_toggle_main":
                        cfg.ally_agents_enabled = not bool(cfg.ally_agents_enabled)
                        continue
                    if action == "ally_count_main":
                        cfg.ally_agents_count = max(0, min(8, int(cfg.ally_agents_count)))
                        continue
                    return MenuResult(action, cfg.copy())
                selected_by_page[page_idx] = selected

        t += 1
        _draw_background(screen, t)

        title = _render_label(title_font, "ASALTO NINJA EN LA ALDEA", (252, 218, 132))
        subtitle = _render_label(subtitle_font, "Menu principal separado por secciones", (208, 228, 198))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 30))
        screen.blit(subtitle, (SCREEN_WIDTH // 2 - subtitle.get_width() // 2, 96))

        list_rect = pygame.Rect(66, 142, SCREEN_WIDTH - 132, 432)
        _draw_card(screen, list_rect, (28, 38, 30), border=(164, 196, 142), border_width=3)

        page_left = _render_label(small_font, "<", (210, 236, 192))
        page_text = _render_label(small_font, f"Seccion {page_idx + 1}/{len(pages)} - {pages[page_idx][0]}", (226, 238, 218))
        page_right = _render_label(small_font, ">", (210, 236, 192))
        screen.blit(page_left, (list_rect.right - 300, list_rect.y + 8))
        screen.blit(page_text, (list_rect.right - 282, list_rect.y + 8))
        screen.blit(page_right, (list_rect.right - 18, list_rect.y + 8))

        rows_start_y = list_rect.y + 42
        row_h = 42
        row_step = 48
        desc_y = list_rect.bottom - 30

        for idx, (action, label, description) in enumerate(rows):
            row_rect = pygame.Rect(list_rect.x + 16, rows_start_y + idx * row_step, list_rect.width - 32, row_h)
            selected_row = idx == selected
            row_fill = (58, 80, 58) if selected_row else (36, 50, 38)
            row_border = (226, 244, 208) if selected_row else (94, 122, 90)
            _draw_card(screen, row_rect, row_fill, border=row_border, border_width=2)

            left = _render_label(option_font, label, (248, 248, 244) if selected_row else (220, 230, 216))
            screen.blit(left, (row_rect.x + 10, row_rect.y + 6))

            if action in ("play_sandbox", "play_agent_sandbox"):
                value = _render_label(option_font, f"enemigos: {cfg.sandbox_enemy_count}", (255, 214, 118))
                screen.blit(value, (row_rect.right - value.get_width() - 10, row_rect.y + 6))
            elif action == "scenario_select":
                value = _render_label(option_font, enemy_scenario_label(cfg.enemy_scenario, short=True), (255, 214, 118))
                screen.blit(value, (row_rect.right - value.get_width() - 10, row_rect.y + 6))
            elif action == "ally_toggle_main":
                value = _render_label(option_font, "SI" if cfg.ally_agents_enabled else "NO", (255, 214, 118))
                screen.blit(value, (row_rect.right - value.get_width() - 10, row_rect.y + 6))
            elif action == "ally_count_main":
                value = _render_label(option_font, str(max(0, int(cfg.ally_agents_count))), (255, 214, 118))
                screen.blit(value, (row_rect.right - value.get_width() - 10, row_rect.y + 6))
            elif action == "play_agent_selected":
                map_name = {
                    "level_1": "Nivel 1",
                    "level_2": "Nivel 2",
                    "level_3": "Nivel 3",
                    "sandbox": "Sandbox",
                }.get(cfg.training_level, cfg.training_level)
                value = _render_label(option_font, map_name, (255, 214, 118))
                screen.blit(value, (row_rect.right - value.get_width() - 10, row_rect.y + 6))

            if selected_row:
                desc_text = description
                if action == "scenario_select":
                    desc_text = enemy_scenario_label(cfg.enemy_scenario, short=False)
                elif action == "ally_toggle_main":
                    desc_text = "Solo aplica en mixed_vs_many_agents / human_vs_many_agents"
                elif action == "ally_count_main":
                    if not cfg.ally_agents_enabled:
                        desc_text = "Aliados desactivados (activalos para que aparezcan)"
                    else:
                        desc_text = "Cantidad de aliados visibles y de apoyo"
                elif action == "play_agent_selected":
                    desc_text = "Ajusta nivel con IZQ/DER y ejecuta con ENTER"
                desc = _render_label(small_font, desc_text, (196, 222, 188))
                screen.blit(desc, (list_rect.x + 18, desc_y))

        right_panel = pygame.Rect(SCREEN_WIDTH - 360, 586, 294, 90)
        _draw_card(screen, right_panel, (30, 44, 33), border=(118, 152, 108), border_width=2)
        quick1 = _render_label(small_font, f"Sandbox enemigos: {cfg.sandbox_enemy_count}", (226, 236, 222))
        quick2 = _render_label(small_font, f"Escenario: {enemy_scenario_label(cfg.enemy_scenario, short=True)}", (226, 236, 222))
        quick3 = _render_label(small_font, f"Demo nivel: {cfg.training_level}", (226, 236, 222))
        ally_text = f"Aliados: {'ON' if cfg.ally_agents_enabled else 'OFF'} x{cfg.ally_agents_count}"
        quick4 = _render_label(small_font, ally_text, (226, 236, 222))
        screen.blit(quick1, (right_panel.x + 10, right_panel.y + 8))
        screen.blit(quick2, (right_panel.x + 10, right_panel.y + 28))
        screen.blit(quick3, (right_panel.x + 10, right_panel.y + 48))
        screen.blit(quick4, (right_panel.x + 10, right_panel.y + 68))

        footer = _render_label(
            small_font,
            "ENTER confirmar | UP/DOWN navegar | LEFT/RIGHT ajustar | TAB/Q/E cambiar seccion",
            (166, 190, 160),
        )
        screen.blit(footer, (SCREEN_WIDTH // 2 - footer.get_width() // 2, SCREEN_HEIGHT - 24))

        pygame.display.flip()
        clock.tick(60)
