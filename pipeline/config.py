from __future__ import annotations

from pipeline.types import PipelineConfig


SUPPORTED_INITIALIZERS = {"clarke_wright", "trivial"}
SUPPORTED_IMPROVERS = {None, "destroy_repair"}


def validate_pipeline_config(config: PipelineConfig) -> None:
    if config.initializer not in SUPPORTED_INITIALIZERS:
        raise ValueError(f"Unsupported initializer: {config.initializer}")

    if config.improver not in SUPPORTED_IMPROVERS:
        raise ValueError(f"Unsupported improver: {config.improver}")

    if config.improver == "destroy_repair" and not config.initializer:
        raise ValueError("Destroy & Repair requires an initializer.")

    if config.max_solutions <= 0:
        raise ValueError("max_solutions must be positive.")
