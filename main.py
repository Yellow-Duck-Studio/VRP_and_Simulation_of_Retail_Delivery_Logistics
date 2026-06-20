from __future__ import annotations

from pathlib import Path

from dataio.loader import load_task_contexts, resolve_data_dir
from experiments.presets import PIPELINE_PRESETS
from pipeline.runner import run_pipeline
from pipeline.serializer import save_pipeline_run


def main() -> None:
    base_dir = Path(__file__).resolve().parent
    data_dir = resolve_data_dir(base_dir)
    output_dir = data_dir / "pipeline_runs"

    task_contexts = load_task_contexts(data_dir)
    selected_presets = [
        "clarke_only",
        "clarke_then_destroy_repair",
        "trivial_then_destroy_repair",
    ]

    print("Running clustering pipelines...")
    for task_context in task_contexts:
        print(f"\nTask {task_context.task_id}: {len(task_context.orders)} orders")

        for preset_name in selected_presets:
            config = PIPELINE_PRESETS[preset_name]
            run_result = run_pipeline(task_context, config)
            output_path = output_dir / preset_name / f"task_{task_context.task_id}.json"
            save_pipeline_run(run_result, output_path)

            print(
                f"  {preset_name}: "
                f"{run_result.summary['valid_solutions']} valid / "
                f"{run_result.summary['total_solutions']} total | "
                f"best={run_result.summary['best_fitness_score']}"
            )

    print(f"\nPipeline results saved under: {output_dir}")


if __name__ == "__main__":
    main()
