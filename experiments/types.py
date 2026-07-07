from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ExperimentConfig:
    algorithms: list[str]
    execution_mode: str = "standalone"
    fitness_version: str = "business_v1"
    fitness_overrides: dict[str, float] = field(default_factory=dict)
    generations: int = 500
    population_size: int = 50
    label: str = "manual_run"


@dataclass(frozen=True)
class AlgorithmSummary:
    algorithm: str
    total_tasks: int
    total_clusterizations: int
    valid_clusterizations: int
    best_fitness_score: float | None
    average_fitness_score: float | None
    output_json: str
    output_csv: str


@dataclass(frozen=True)
class ExperimentRunManifest:
    run_id: str
    label: str
    execution_mode: str
    fitness_version: str
    fitness_overrides: dict[str, float]
    generations: int
    population_size: int
    algorithms: list[str]
    summaries: list[AlgorithmSummary]
    metadata: dict[str, Any] = field(default_factory=dict)
