# Smart-Top-Down-Game (Atraco Táctico)

Un juego de acción-sigilo en perspectiva superior (2D top-down) inspirado en títulos como Hotline Miami. El juego se enfoca en movimiento táctico, detección de enemigos y entornos interactivos.

## Índice

- [Estructura del Proyecto](#estructura-del-proyecto)
- [Módulos Principales](#módulos-principales)
- [Instalación y Configuración](#instalación-y-configuración)
- [Ejecución](#ejecución)
- [Componentes del Juego](#componentes-del-juego)
- [Sistemas de IA](#sistemas-de-ia)
- [Mapas y Assets](#mapas-y-assets)

## Estructura del Proyecto

```
Atraco_Tactico/
├── main.py                 # Punto de entrada principal (menú + sandbox + entrenamiento)
├── config/
│   └── settings.py         # Configuraciones globales (pantalla, colores, FPS, rutas)
├── core/                   # Lógica principal del juego
│   ├── player.py           # Clase Player - controlador del jugador
│   ├── enemy.py            # Clases Enemy (TypeA, TypeB, TypeC)
│   ├── bullet.py           # Clase Bullet - proyectiles
│   ├── potion.py           # Clase Potion - pociones curativas
│   ├── spike.py            # Clase Spike - pinchos dañinos
│   ├── wall.py             # Clase Wall - paredes
│   ├── world.py            # Clase World - gestión del mundo del juego
│   └── item_manager.py     # Gestión de items y recolectables
├── ai/                     # Módulos de IA y machine learning
│   ├── fsm_enemies.py      # Máquina de estados finita para enemigos
│   ├── genetic_algorithm.py # Algoritmo genético para evolución
│   ├── neural_network.py    # Red neuronal para decisiones de IA
│   ├── rl_agent.py         # Agente de refuerzo (RL) - controlador automático
│   ├── sensors.py          # Sensores para enemigos y agentes
│   └── actuators.py        # Actuadores para movimiento y acciones
├── systems/                # Sistemas de juego
│   ├── collision.py        # Detección de colisiones
│   ├── pathfinding.py      # Búsqueda de rutas (A*)
│   └── vision.py           # Sistema de visión para enemigos
├── infrastructure/         # Componentes de infraestructura
│   ├── renderer.py         # Motor de renderizado (cámara, sprites)
│   ├── input_handler.py    # Procesamiento de entrada del usuario
│   ├── map_loader.py       # Cargador de mapas (Tiled)
│   ├── menu_screen.py      # Pantalla del menú
│   └── sandbox_map.py      # Constructor de mapa sandbox
├── assets/                 # Recursos multimedia
│   ├── maps/               # Archivos de mapas Tiled (.tmx, .tsj)
│   ├── player/             # Sprites del jugador por animación
│   ├── sprites/            # Otros sprites del juego
│   ├── sounds/             # Efectos de sonido
│   └── tilesets/           # Tilesets para mapas
├── data/                   # Datos del juego
│   ├── logs/               # Archivos de log
│   └── models/             # Modelos entrenados de IA
├── tests/                  # Suite de pruebas
│   └── test_alpha.py       # Pruebas alpha
├── training_reports/       # Reportes de entrenamiento
├── benchmark_reports/      # Reportes de benchmark
├── utils/
│   └── math_utils.py       # Utilidades matemáticas
├── requirements.txt        # Dependencias de Python
└── README.md              # Este archivo
```

## 🎮 Módulos Principales

### core/player.py
**Clase: Player**
- Controla el movimiento, rotación y acciones del jugador
- Gestiona animaciones (idle, walk, attack, defend, hit, death, shoot)
- Sistema de salud y armadura
- Disparo de balas y uso de pociones
- Interacción con objetos del mundo

### core/enemy.py
**Clases: EnemyTypeA, EnemyTypeB, EnemyTypeC**
- Tres tipos de enemigos con comportamientos diferentes
- Sistema FSM (Finite State Machine) para IA
- Patrullas automáticas y persecución del jugador
- Combate cercano y a distancia
- Animaciones de movimiento y ataque

### core/world.py
**Clase: World**
- Gestión del estado general del mundo
- Administración de jugadores, enemigos, balas y objetos
- Actualización de lógica de juego
- Gestión de colisiones y eventos

### ai/rl_agent.py
**Clase: AutoPlayerAgent**
- Agente entrenado con aprendizaje por refuerzo
- Red neuronal para toma de decisiones
- Integración con el sistema de juego
- Modo automático de juego

### ai/genetic_algorithm.py
**Funciones principales:**
- `create_population()` - Crea una población inicial
- `evolve_population()` - Evoluciona la población generación tras generación
- `Genome` - Representa un individuo evolucionable
- Configuración de generaciones, mutación y selección

### systems/pathfinding.py
**Función: build_route_hint()**
- Implementa algoritmo A* para búsqueda de rutas
- Utilizado por enemigos para navegación inteligente

### infrastructure/renderer.py
**Clases: Renderer, Camera**
- Motor de renderizado basado en Pygame
- Sistema de cámara para seguimiento
- Renderizado de capas y efectos visuales

### infrastructure/map_loader.py
**Clase: MapLoader**
- Carga mapas en formato Tiled (.tmx)
- Parseo de tilesets y capas
- Generación de geometría de colisión

## 🤖 Sistemas de IA

### FSM (Máquina de Estados Finita)
- Estados: IDLE, PATROL, PURSUIT, ATTACK, HIT, DEATH
- Transiciones automáticas basadas en condiciones

### Algoritmo Genético
- Evoluciona genomas de comportamiento
- Selección por fitness
- Mutación y reproducción

### Red Neuronal
- Entrada: sensores (distancia, ángulo, salud, etc.)
- Salida: decisiones de movimiento y ataque
- Entrenamiento por refuerzo

### Aprendizaje por Refuerzo
- Recompensas por objetivos completados
- Penalizaciones por daño recibido
- Converge a estrategias óptimas

## 🗺️ Mapas y Assets

### Mapas Disponibles
- `Mapa1.tmx` - Mapa principal de juego
- `MapProd1.tmx`, `MapProd2.tmx` - Mapas de producción
- Sandbox - Mapa generado proceduralmente para pruebas

### Tilesets
- `TX Tileset Grass.tsx` - Piso de pasto
- `TX Tileset Stone Ground.tsx` - Piso de piedra
- `Water_tiles.tsx` - Teselas de agua
- Pixel Art Top Down - Asset pack profesional

### Animaciones de Jugador
Carpetas organizadas por tipo:
- `idle/` - Reposo
- `walk/` - Caminata
- `attack/` - Ataque cuerpo a cuerpo
- `shoot/` - Disparo
- `defend/` - Defensa
- `hit/` - Golpe recibido
- `death/` - Muerte

## 📦 Instalación y Configuración

### Requisitos
- Python 3.13+
- Pygame
- NumPy
- Otras dependencias en `requirements.txt`

### Instalación
```bash
# Clonar repositorio
git clone https://github.com/Math-Git-05/Smart-Top-Down-Game.git
cd Atraco_Tactico

# Instalar dependencias
pip install -r requirements.txt
```

### Configuración
Editar `config/settings.py` para:
- Resolución de pantalla (SCREEN_WIDTH, SCREEN_HEIGHT)
- FPS objetivo
- Rutas de recursos
- Colores y constantes de juego

## ▶️ Ejecución

### Menú Principal
```bash
python main.py
```
Opciones:
1. **Play** - Juega como jugador humano
2. **Sandbox** - Sandbox interactivo
3. **Train Agent** - Entrena el agente RL
4. **Benchmark** - Ejecuta pruebas de rendimiento
5. **Exit** - Salir

### Entrenamiento
```python
# El entrenamiento genera reportes en training_reports/
# Formato: training_[nivel]_[timestamp].txt
```

### Benchmarks
```python
# Los benchmarks generan reportes en benchmark_reports/
# Formato: benchmark_[timestamp].txt
```

## 🎯 Componentes de Juego

### Jugador
- **Salud**: 100 HP
- **Armadura**: Reduce daño
- **Arma**: Pistola con munición ilimitada
- **Pociones**: Recuperan salud

### Enemigos
- **TypeA**: Enemigo básico, ataque cercano
- **TypeB**: Enemigo de rango, dispara proyectiles
- **TypeC**: Enemigo avanzado, combinación de ambos

### Objetos del Mundo
- **Cofres**: Contienen items
- **Puertas**: Bloques de paso
- **Pinchos**: Dañan al contacto
- **Pociones**: Curación

## 📊 Reportes y Logs

### Training Reports
Contienen métricas de entrenamiento:
- Episodio
- Recompensa acumulada
- Tiempo
- Enemigos derrotados
- Daño recibido

### Benchmark Reports
Miden rendimiento:
- FPS promedio
- Tiempo de ejecución
- Uso de memoria
- Optimizaciones activas

## 🔧 Configuración Avanzada

### Parámetros RL Agent
En `ai/rl_agent.py`:
- Learning rate
- Epsilon para exploración
- Factor de descuento (gamma)
- Tamaño de batch

### Parámetros Genéticos
En `ai/genetic_algorithm.py`:
- Tamaño de población
- Tasa de mutación
- Número de generaciones
- Elitismo

### Sensores
En `ai/sensors.py`:
- Rango de visión
- Precisión de sensores
- Ruido ambiental

## 📝 Licencia

Este proyecto es parte del desarrollo de Smart-Top-Down-Game.

## 👨‍💻 Autor

Mathias (Math-Git-05)

---

**Última actualización**: Abril 2026

## Implementacion real de algoritmos (RL + Genetico)

Esta seccion documenta la implementacion actual del proyecto, alineada a la guia del profesor (sensores, actuadores, fitness, cruce/mutacion/seleccion, pathfinding y validacion por benchmark).
En el marco del PDF del profesor, el entrenamiento reforzado se modela de forma implicita a traves de recompensa (fitness) + optimizacion genetica.

### 1) Agente tipo RL (politica de decision)
- Archivo principal: `ai/rl_agent.py`
- Clase: `AutoPlayerAgent`
- Sensores usados por la politica:
  - Distancia y direccion al enemigo mas cercano
  - Salud (`hp_ratio`) y energia (`energy_ratio`)
  - Riesgo de hongos (`hazard_rects`) con evasion activa
  - Estado de bloqueo/stuck y oscilacion de movimiento
  - Disponibilidad de pociones (`ItemManager.get_active_potion_positions`)
- Actuadores (salidas):
  - Movimiento en X/Y
  - Ataque melee
  - Defensa
  - Ataque ranged (target point)

### 2) Optimizador genetico (entrenamiento)
- Motor genetico: `ai/genetic_algorithm.py`
  - `create_population()`
  - `evolve_population()`
  - `Genome` y `GeneticConfig`
- Integracion de entrenamiento y evaluacion: `main.py`
  - `train_agent()`
  - `_fitness_from_result()`
  - `run_benchmark()`
- Operadores ya implementados:
  - Seleccion: `tournament`, `roulette`, `rank`
  - Cruce: `uniform`, `single_point`, `blend`
  - Mutacion por gen con `mutation_rate` + `mutation_scale`

### 3) Fitness (recompensa de entrenamiento)
- Definido en `main.py` dentro de `_fitness_from_result(result)`.
- Prioriza kills y dano, luego supervivencia/progreso.
- Penaliza stuck, oscilacion, timeout, hongos y falta de progreso.

### 4) Pathfinding y navegacion
- A* en `systems/pathfinding.py` (`build_route_hint`, `astar_tiles`).
- Enemigos con persecucion reactiva y rodeo de obstaculos:
  - `core/enemy.py` -> `_move_toward_reactive()`
- Agente con anti-stuck y detour lateral:
  - `ai/rl_agent.py` -> `_pick_stalking_detour()`, `_pick_navigable_move()`

### 5) FSM de enemigos (tipos A/B/C)
- Implementada en `core/enemy.py` mediante estados/roles por tipo:
  - Tipo A: persecucion + melee + busqueda de vida en low HP
  - Tipo B: ataque a distancia + defensa a corta distancia
  - Tipo C: ranged + flee/counter + busqueda de vida en low HP

### 6) Benchmark y reportes
- Entrenamiento: `training_reports/training_*.txt`
- Benchmark: `benchmark_reports/benchmark_*.txt`
- Perfil ganador persistente para demos:
  - `training_reports/winning_agent_profile.json`
