from pipeline.types import PipelineConfig


PIPELINE_PRESETS = {
    "clarke_only": PipelineConfig(
        initializer="clarke_wright",
        improver=None,
    ),
    "clarke_then_destroy_repair": PipelineConfig(
        initializer="clarke_wright",
        improver="destroy_repair",
        improver_config={
            "iterations": 250,
            "destroy_fraction": 0.2,
            "max_solutions": 100,
            "rng_seed": 42,
        },
        max_solutions=100,
    ),
    "trivial_then_destroy_repair": PipelineConfig(
        initializer="trivial",
        improver="destroy_repair",
        improver_config={
            "iterations": 250,
            "destroy_fraction": 0.2,
            "max_solutions": 100,
            "rng_seed": 42,
        },
        max_solutions=100,
    ),
}
