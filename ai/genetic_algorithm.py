from __future__ import annotations

from dataclasses import dataclass, field
import random
from typing import Iterable

GENE_ORDER = (
    "aggression",
    "survival",
    "objective",
    "spacing",
    "aim",
    "stalking",
    "unstuck",
)


@dataclass(slots=True)
class Genome:
    genes: dict[str, float]
    fitness: float = 0.0

    def copy(self) -> "Genome":
        return Genome(genes=dict(self.genes), fitness=float(self.fitness))


@dataclass(slots=True)
class GeneticConfig:
    population_size: int = 8
    generations: int = 4
    crossover_mode: str = "uniform"  # uniform | single_point | blend
    selection_mode: str = "tournament"  # tournament | roulette | rank
    mutation_rate: float = 0.15
    mutation_scale: float = 0.25
    elitism_ratio: float = 0.25
    gene_min: float = -2.0
    gene_max: float = 2.0


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


def _base_genes() -> dict[str, float]:
    return {
        "aggression": 1.0,
        "survival": 1.0,
        "objective": 1.2,
        "spacing": 0.8,
        "aim": 1.0,
        "stalking": 1.0,
        "unstuck": 1.0,
    }


def default_genome() -> Genome:
    return Genome(genes=_base_genes())


def random_genome(config: GeneticConfig, rng: random.Random) -> Genome:
    genes = _base_genes()
    for name in GENE_ORDER:
        genes[name] = _clamp(
            genes[name] + rng.uniform(-0.9, 0.9),
            config.gene_min,
            config.gene_max,
        )
    return Genome(genes=genes)


def create_population(config: GeneticConfig, rng: random.Random) -> list[Genome]:
    size = max(2, int(config.population_size))
    return [random_genome(config, rng) for _ in range(size)]


def _crossover(parent_a: Genome, parent_b: Genome, config: GeneticConfig, rng: random.Random) -> Genome:
    mode = (config.crossover_mode or "uniform").strip().lower()
    child: dict[str, float] = {}
    defaults = _base_genes()

    if mode == "single_point":
        split = rng.randint(1, len(GENE_ORDER) - 1)
        for idx, name in enumerate(GENE_ORDER):
            source = parent_a if idx < split else parent_b
            child[name] = float(source.genes.get(name, defaults[name]))
    elif mode == "blend":
        for name in GENE_ORDER:
            alpha = rng.uniform(0.25, 0.75)
            a_val = float(parent_a.genes.get(name, defaults[name]))
            b_val = float(parent_b.genes.get(name, defaults[name]))
            child[name] = (a_val * alpha) + (b_val * (1.0 - alpha))
    else:
        for name in GENE_ORDER:
            if rng.random() < 0.5:
                child[name] = float(parent_a.genes.get(name, defaults[name]))
            else:
                child[name] = float(parent_b.genes.get(name, defaults[name]))

    return Genome(genes=child)


def _mutate(genome: Genome, config: GeneticConfig, rng: random.Random) -> Genome:
    mutated = genome.copy()
    rate = _clamp(float(config.mutation_rate), 0.0, 1.0)
    scale = max(0.0, float(config.mutation_scale))
    defaults = _base_genes()

    for name in GENE_ORDER:
        if name not in mutated.genes:
            mutated.genes[name] = float(defaults[name])
        if rng.random() > rate:
            continue
        delta = rng.uniform(-scale, scale)
        mutated.genes[name] = _clamp(
            mutated.genes[name] + delta,
            config.gene_min,
            config.gene_max,
        )
    return mutated


def _select_parent(pool: list[Genome], config: GeneticConfig, rng: random.Random) -> Genome:
    mode = (config.selection_mode or "tournament").strip().lower()
    if not pool:
        raise ValueError("selection pool is empty")
    if len(pool) == 1:
        return pool[0]

    if mode == "roulette":
        min_fit = min(g.fitness for g in pool)
        shift = -min_fit if min_fit < 0 else 0.0
        weights = [(g.fitness + shift + 1e-6) for g in pool]
        total = sum(weights)
        if total <= 1e-12:
            return rng.choice(pool)
        pick = rng.uniform(0.0, total)
        acc = 0.0
        for genome, weight in zip(pool, weights):
            acc += weight
            if acc >= pick:
                return genome
        return pool[-1]

    if mode == "rank":
        ranked = sorted(pool, key=lambda g: g.fitness, reverse=True)
        n = len(ranked)
        # Highest rank gets highest weight n, next n-1, ...
        total = (n * (n + 1)) / 2
        pick = rng.uniform(0.0, total)
        acc = 0.0
        for rank, genome in enumerate(ranked):
            weight = float(n - rank)
            acc += weight
            if acc >= pick:
                return genome
        return ranked[-1]

    # tournament (default)
    k = min(4, len(pool))
    contenders = rng.sample(pool, k)
    return max(contenders, key=lambda g: g.fitness)


def evolve_population(
    scored_population: Iterable[Genome],
    config: GeneticConfig,
    rng: random.Random,
) -> list[Genome]:
    ranked = sorted((gen.copy() for gen in scored_population), key=lambda g: g.fitness, reverse=True)
    if not ranked:
        return create_population(config, rng)

    population_size = max(2, int(config.population_size))
    elite_count = max(1, int(population_size * max(0.05, min(0.7, config.elitism_ratio))))
    elites = [g.copy() for g in ranked[:elite_count]]

    survivor_pool = ranked[: max(2, int(population_size * 0.5))]
    next_population: list[Genome] = [g.copy() for g in elites]

    while len(next_population) < population_size:
        parent_a = _select_parent(survivor_pool, config, rng)
        parent_b = _select_parent(survivor_pool, config, rng)
        child = _crossover(parent_a, parent_b, config, rng)
        child = _mutate(child, config, rng)
        next_population.append(child)

    return next_population[:population_size]
