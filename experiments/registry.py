from __future__ import annotations

from evolutionary_algorithm.domain import Algorithms


ALGORITHM_REGISTRY = {
    "dbscan": Algorithms.DBSCAN,
    "sweep": Algorithms.SWEEP,
    "clarke_wright": Algorithms.CLWR,
    "destroy_repair": Algorithms.DSTR,
    "random": Algorithms.RND,
}


def resolve_algorithm(name: str) -> Algorithms:
    key = name.strip().lower()
    if key not in ALGORITHM_REGISTRY:
        raise ValueError(f"Unknown algorithm name: {name}")
    return ALGORITHM_REGISTRY[key]
