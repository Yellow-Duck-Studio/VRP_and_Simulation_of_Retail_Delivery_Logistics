from .config import validate_pipeline_config
from .types import (
    ConstraintData,
    MetricsResult,
    PipelineConfig,
    PipelineRunResult,
    Solution,
    TaskContext,
    TripResult,
)

__all__ = [
    "ConstraintData",
    "MetricsResult",
    "PipelineConfig",
    "PipelineRunResult",
    "Solution",
    "TaskContext",
    "TripResult",
    "run_pipeline",
    "validate_pipeline_config",
]


def __getattr__(name):
    if name == "run_pipeline":
        from .runner import run_pipeline
        return run_pipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")