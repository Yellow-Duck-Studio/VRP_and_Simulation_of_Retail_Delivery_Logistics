from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FitnessConfig:
    version: str
    capacity_penalty_weight: float = 1000.0
    mass_penalty_weight: float = 500.0
    sla_penalty_weight: float = 100.0
    sync_weight: float = 50.0
    fleet_weight: float = 2.0
    direction_weight: float = 5.0


FITNESS_REGISTRY = {
    "business_v1": FitnessConfig(version="business_v1"),
    "basic_v1": FitnessConfig(
        version="basic_v1",
        sync_weight=0.0,
        fleet_weight=0.0,
        direction_weight=0.0,
    ),
}


def resolve_fitness_config(
    version: str = "business_v1",
    overrides: dict | None = None,
) -> FitnessConfig:
    if version not in FITNESS_REGISTRY:
        raise ValueError(f"Unknown fitness version: {version}")

    base = asdict(FITNESS_REGISTRY[version])
    if overrides:
        base.update(overrides)
    return FitnessConfig(**base)
