from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from pipeline.types import PipelineRunResult


def pipeline_run_to_dict(run_result: PipelineRunResult) -> dict:
    return asdict(run_result)


def save_pipeline_run(run_result: PipelineRunResult, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(pipeline_run_to_dict(run_result), file, indent=4)
