"""
logger.py — Pretty structured logger for the delivery clustering & routing system.

Covers every layer of the project:
  - Evolutionary Algorithm : generation stats, mutation tracking, archive growth
  - DBSCAN seeding         : eps candidates, cluster/noise/split events
  - Heuristics             : Clarke-Wright merges, Destroy-Repair iterations
  - Pipeline               : stage transitions, timing, solution tables
  - Fitness                : full component breakdown

─────────────────────────────── Quick-start ───────────────────────────────
from logger import get_logger, ea_log, cluster_log, heuristics_log, pipeline_log, fitness_log

log = get_logger(__name__)          # standard Python logger backed by rich
log.info("Task %s loaded", task_id)

ea_log.algorithm_start("DBSCAN", orders=120, warehouses=3, pop=50, gens=500)
ea_log.generation(gen, population, archive_size=len(archive))

cluster_log.dbscan_result(wh_id=1, transport="car", eps=300, min_s=2, n_clusters=8, n_noise=3)

heuristics_log.cw_done(n_routes=12, fitness=34.7, is_valid=True)
heuristics_log.dr_done(n_solutions=87, best_fitness=28.1, elapsed_s=4.3)

pipeline_log.pipeline_summary(run_result)      # prints a solution table
fitness_log.fitness_breakdown("task_1_cw_001", components)
──────────────────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional

from rich import box
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.theme import Theme


# ─────────────────────────────────────────────────────────────────────────────
# 1. Console & Theme
# ─────────────────────────────────────────────────────────────────────────────

_THEME = Theme({
    # log levels
    "log.level.debug":    "dim white",
    "log.level.info":     "bold green",
    "log.level.warning":  "bold yellow",
    "log.level.error":    "bold red",
    # fitness colours
    "fitness.good":       "bold green",
    "fitness.ok":         "yellow",
    "fitness.bad":        "bold red",
    # domain colours
    "stage":              "bold cyan",
    "gen.hdr":            "bold magenta",
    "cluster.eps":        "cyan",
    "cluster.noise":      "yellow",
    "cluster.ok":         "green",
    "metric.penalty":     "red",
    "metric.time":        "blue",
    "metric.distance":    "cyan",
    "badge.valid":        "bold green",
    "badge.invalid":      "bold red",
})

console = Console(theme=_THEME, highlight=False)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Root logging bootstrap
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a rich handler. Call once at app startup."""
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                tracebacks_show_locals=False,
                show_path=False,
                markup=True,
                log_time_format="[%X]",
            )
        ],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    """Return a named logger (auto-configures rich on first import)."""
    return logging.getLogger(name)


# Auto-configure on first import so callers don't need to call setup_logging().
setup_logging()


# ─────────────────────────────────────────────────────────────────────────────
# 3. Shared helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fitness_style(score: float, good: float = 50.0, bad: float = 200.0) -> str:
    if score <= good:
        return "fitness.good"
    if score >= bad:
        return "fitness.bad"
    return "fitness.ok"


def _valid_badge(is_valid: bool) -> Text:
    return (
        Text(" ✓ VALID ", style="bold white on green")
        if is_valid
        else Text(" ✗ INVALID ", style="bold white on red")
    )


def _fmt(v: float, p: int = 3) -> str:
    return f"{v:.{p}f}"


def _delta_str(before: float, after: float) -> str:
    d = after - before
    sign, color = ("▼", "green") if d < 0 else ("▲", "red")
    return f"[{color}]{sign}{abs(d):.3f}[/]"


# ─────────────────────────────────────────────────────────────────────────────
# 4. EvolutionLogger
# ─────────────────────────────────────────────────────────────────────────────

class EvolutionLogger:
    """
    Attaches to run_evolutionary_clustering().

    Integration points
    ──────────────────
    # Top of run_evolutionary_clustering():
    ea_log.algorithm_start(algorithm.name, len(orders), len(warehouses_dict), population_size, generations)

    # After population init:
    ea_log.population_initialized(algorithm.name, len(population), elapsed)

    # Inside the generation loop (replace the existing print):
    ea_log.generation(gen, population, len(valid_clusterizations_archive))

    # After mutate():
    ea_log.mutation_applied(mutation_type, old_fitness, child.fitness_score)

    # After the loop:
    ea_log.evolution_done(generations, len(valid_clusterizations_archive), elapsed)
    """

    _log = get_logger("ea")

    # ── startup ──────────────────────────────────────────────────────────────

    def algorithm_start(
            self,
            algorithm: str,
            orders: int,
            warehouses: int,
            pop: int,
            gens: int,
    ) -> None:
        tbl = Table(box=box.ROUNDED, show_header=False, padding=(0, 2), expand=False)
        tbl.add_column("k", style="dim")
        tbl.add_column("v", style="bold")
        tbl.add_row("Algorithm",      f"[bold cyan]{algorithm}[/]")
        tbl.add_row("Orders",         str(orders))
        tbl.add_row("Warehouses",     str(warehouses))
        tbl.add_row("Population",     str(pop))
        tbl.add_row("Generations",    str(gens))
        console.print(
            Panel(tbl, title="[bold magenta]Evolutionary Algorithm — Start[/]", expand=False)
        )

    def population_initialized(
            self,
            algorithm: str,
            size: int,
            elapsed_s: float,
    ) -> None:
        self._log.info(
            f"[stage]Init[/] [bold]{algorithm}[/] → "
            f"[bold]{size}[/] individuals in [dim]{elapsed_s:.2f}s[/]"
        )

    # ── per-generation ────────────────────────────────────────────────────────

    def generation(
            self,
            gen: int,
            population: list,        # List[Individual] — duck-typed, no domain import needed
            archive_size: int,
            log_interval: int = 10,
    ) -> None:
        """Log one generation line. Set log_interval=1 for full verbosity."""
        if gen % log_interval != 0:
            return
        scores = [
            ind.fitness_score
            for ind in population
            if ind.fitness_score != float("inf")
        ]
        if not scores:
            return

        best = scores[0]
        avg  = sum(scores) / len(scores)
        valid_in_pop = sum(1 for ind in population if ind.is_valid)
        color = _fitness_style(best)

        self._log.info(
            f"[gen.hdr]Gen {gen:>5}[/] │ "
            f"best [{color}]{best:>10.3f}[/] │ "
            f"avg [dim]{avg:>10.3f}[/] │ "
            f"valid [bold]{valid_in_pop:>3}/{len(population)}[/] │ "
            f"archive [bold green]{archive_size:>5}[/]"
        )

    def mutation_applied(
            self,
            mutation_type: str,
            before: float,
            after: float,
    ) -> None:
        """DEBUG-level; call inside mutate() for fine-grained tracking."""
        color = "green" if after < before else "red"
        self._log.debug(
            f"  mut [bold]{mutation_type:<16}[/] "
            f"{before:.3f} → [{color}]{after:.3f}[/]  {_delta_str(before, after)}"
        )

    def crossover_applied(self, child_fitness: float) -> None:
        """DEBUG-level; call after crossover() + evaluate."""
        color = _fitness_style(child_fitness)
        self._log.debug(f"  crossover child fitness=[{color}]{child_fitness:.3f}[/]")

    def elitism(self, kept: int) -> None:
        self._log.debug(f"  elitism: keeping top [bold]{kept}[/]")

    # ── completion ────────────────────────────────────────────────────────────

    def evolution_done(
            self,
            generations: int,
            archive_size: int,
            elapsed_s: float,
    ) -> None:
        console.print(
            Panel(
                f"[bold]Generations completed:[/] {generations}   "
                f"[bold]Archive size:[/] [bold green]{archive_size}[/]   "
                f"[bold]Wall time:[/] {elapsed_s:.1f}s",
                title="[bold magenta]Evolution Complete ✓[/]",
                expand=False,
            )
        )

    # ── context manager (live progress bar) ──────────────────────────────────

    @contextmanager
    def generation_progress(self, total: int) -> Iterator[Progress]:
        """
        Wraps the generation loop with a live Rich progress bar.

        Usage:
            with ea_log.generation_progress(generations) as bar:
                for gen in range(generations):
                    ...
                    bar.advance(bar._task, best=pop[0].fitness_score, archive=len(archive))
        """
        with Progress(
                SpinnerColumn(),
                TextColumn("[bold magenta]Gen {task.fields[gen]:>5}[/]"),
                BarColumn(bar_width=28),
                TaskProgressColumn(),
                TextColumn("best [bold]{task.fields[best]:.3f}[/]"),
                TextColumn("archive [green]{task.fields[archive]}[/]"),
                TimeElapsedColumn(),
                TimeRemainingColumn(),
                console=console,
                transient=False,
                refresh_per_second=4,
        ) as progress:
            task_id = progress.add_task(
                "evolving", total=total, gen=0, best=float("inf"), archive=0
            )
            # Expose task id so callers can call progress.update(task_id, ...)
            progress._managed_task = task_id  # type: ignore[attr-defined]
            yield progress


# ─────────────────────────────────────────────────────────────────────────────
# 5. ClusterLogger
# ─────────────────────────────────────────────────────────────────────────────

class ClusterLogger:
    """
    Attaches to dbscan.py (seed_population, _build_individual, _merge_noise, etc.).

    Integration points
    ──────────────────
    # Top of seed_population():
    cluster_log.seeding_start(len(orders), list(constraints.transport_distribution))

    # In _eps_candidates() or the loop over eps:
    cluster_log.eps_candidates(transport_type, all_eps)

    # In _run_dbscan():
    cluster_log.dbscan_result(wh_id, transport_type, eps, min_samples, n_clusters, n_noise)

    # In _split_oversized():
    cluster_log.split_oversized(original_size, len(result))

    # In _merge_noise():
    cluster_log.noise_merged(n_merged_into_existing, n_new_singles)

    # Bottom of seed_population():
    cluster_log.seeding_done(len(candidates), len(population), padded=population_size - len(candidates))
    """

    _log = get_logger("cluster")

    def seeding_start(self, orders: int, transport_types: List[str]) -> None:
        console.rule(
            f"[bold cyan]DBSCAN Seeding[/]  orders=[bold]{orders}[/]  "
            f"transports=[bold]{', '.join(transport_types)}[/]"
        )

    def eps_candidates(self, transport: str, eps_values: List[float]) -> None:
        vals = ", ".join(f"[cluster.eps]{e:.0f}s[/]" for e in eps_values)
        self._log.debug(f"  [{transport}] eps candidates: {vals}")

    def dbscan_result(
            self,
            wh_id: int,
            transport: str,
            eps: float,
            min_samples: int,
            n_clusters: int,
            n_noise: int,
    ) -> None:
        noise_str = (
            f"[cluster.noise]{n_noise} noise[/]"
            if n_noise
            else "[dim]0 noise[/]"
        )
        self._log.debug(
            f"  wh={wh_id} [{transport}] "
            f"eps=[cluster.eps]{eps:.0f}s[/] min_s={min_samples} → "
            f"[cluster.ok]{n_clusters} clusters[/], {noise_str}"
        )

    def split_oversized(self, original_size: int, resulting_parts: int) -> None:
        self._log.debug(
            f"  [yellow]split[/] oversized cluster "
            f"({original_size} orders → {resulting_parts} parts)"
        )

    def noise_merged(self, n_absorbed: int, n_new_singles: int) -> None:
        self._log.debug(
            f"  [yellow]noise[/] {n_absorbed} absorbed into existing, "
            f"{n_new_singles} became new singles"
        )

    def seeding_done(
            self,
            unique_candidates: int,
            final_population: int,
            padded: int = 0,
    ) -> None:
        pad = f" ([dim]+{padded} random padding[/])" if padded > 0 else ""
        self._log.info(
            f"[stage]DBSCAN seed[/] done — "
            f"[bold]{unique_candidates}[/] unique variants → "
            f"population [bold]{final_population}[/]{pad}"
        )

    def random_padding(self, wh_id: int, chunk_size: int, transport: str) -> None:
        self._log.debug(
            f"  random-pad wh={wh_id}: {chunk_size} orders via [bold]{transport}[/]"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. HeuristicsLogger
# ─────────────────────────────────────────────────────────────────────────────

class HeuristicsLogger:
    """
    Attaches to savings_core.py, destroy_repair_core.py, trivial_initializer.py.

    Integration — Clarke-Wright (savings_core.py)
    ──────────────────────────────────────────────
    heuristics_log.cw_start(len(orders), len(warehouses_dict))
    # inside warehouse loop:
    heuristics_log.cw_savings_computed(warehouse_id, len(savings_candidates))
    # inside savings loop on successful merge:
    heuristics_log.cw_merge(left_order_id, right_order_id, savings_value, len(merged_route.order_ids))
    # after evaluate_individual():
    heuristics_log.cw_done(len(unique_routes), individual.fitness_score, individual.is_valid)

    Integration — Destroy-Repair (destroy_repair_core.py)
    ──────────────────────────────────────────────────────
    heuristics_log.dr_start(current.fitness_score, iterations, destroy_fraction)
    # inside iteration loop:
    heuristics_log.dr_iteration(iteration, best.fitness_score, len(solutions))
    heuristics_log.dr_done(len(solutions), best.fitness_score, elapsed_s)

    Integration — Trivial (trivial_initializer.py)
    ───────────────────────────────────────────────
    heuristics_log.trivial_done(len(task_context.orders), default_transport)
    """

    _log = get_logger("heuristics")

    # ── Clarke-Wright ─────────────────────────────────────────────────────────

    def cw_start(self, orders: int, warehouses: int) -> None:
        self._log.info(
            f"[stage]Clarke-Wright[/] "
            f"{orders} orders across {warehouses} warehouses"
        )

    def cw_savings_computed(self, warehouse_id: int, n_pairs: int) -> None:
        self._log.debug(
            f"  wh={warehouse_id}: [dim]{n_pairs}[/] savings pairs"
        )

    def cw_merge(
            self,
            left_id: int,
            right_id: int,
            saving_km: float,
            new_route_size: int,
    ) -> None:
        self._log.debug(
            f"  merge orders [{left_id}]+[{right_id}] "
            f"saving=[metric.distance]{saving_km:.3f}km[/] "
            f"→ route size {new_route_size}"
        )

    def cw_done(self, n_routes: int, fitness: float, is_valid: bool) -> None:
        color = _fitness_style(fitness)
        badge = _valid_badge(is_valid)
        self._log.info(
            f"[stage]Clarke-Wright[/] done — "
            f"{n_routes} routes, fitness=[{color}]{fitness:.3f}[/] {badge}"
        )

    # ── Destroy-Repair ────────────────────────────────────────────────────────

    def dr_start(
            self,
            seed_fitness: float,
            iterations: int,
            destroy_fraction: float,
    ) -> None:
        color = _fitness_style(seed_fitness)
        self._log.info(
            f"[stage]Destroy-Repair[/] "
            f"seed_fitness=[{color}]{seed_fitness:.3f}[/]  "
            f"iterations={iterations}  "
            f"destroy={destroy_fraction:.0%}"
        )

    def dr_iteration(
            self,
            iteration: int,
            best_fitness: float,
            n_solutions: int,
            log_every: int = 25,
    ) -> None:
        """DEBUG-level; log every `log_every` iterations to avoid spam."""
        if iteration % log_every != 0:
            return
        color = _fitness_style(best_fitness)
        self._log.debug(
            f"  DR iter {iteration:>4} │ "
            f"best=[{color}]{best_fitness:.3f}[/] │ "
            f"solutions={n_solutions}"
        )

    def dr_destroy(self, n_removed: int, target: int) -> None:
        self._log.debug(
            f"    destroy: removed [bold]{n_removed}[/] / target {target} orders"
        )

    def dr_repair(self, order_id: int, inserted_to: str, new_fitness: float) -> None:
        color = _fitness_style(new_fitness)
        self._log.debug(
            f"    repair: order {order_id} → trip {inserted_to}  "
            f"fitness=[{color}]{new_fitness:.3f}[/]"
        )

    def dr_new_solution(self, n_total: int, fitness: float) -> None:
        color = _fitness_style(fitness)
        self._log.info(
            f"  [bold green]★[/] New valid solution #{n_total}  "
            f"fitness=[{color}]{fitness:.3f}[/]"
        )

    def dr_done(
            self,
            n_solutions: int,
            best_fitness: float,
            elapsed_s: float,
    ) -> None:
        color = _fitness_style(best_fitness)
        self._log.info(
            f"[stage]Destroy-Repair[/] done — "
            f"[bold]{n_solutions}[/] valid solutions  "
            f"best=[{color}]{best_fitness:.3f}[/]  "
            f"[dim]{elapsed_s:.2f}s[/]"
        )

    # ── Trivial initializer ───────────────────────────────────────────────────

    def trivial_done(self, n_orders: int, transport_type: str) -> None:
        self._log.info(
            f"[stage]Trivial init[/] — "
            f"{n_orders} single-order trips via [bold]{transport_type}[/]"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. PipelineLogger
# ─────────────────────────────────────────────────────────────────────────────

class PipelineLogger:
    """
    Attaches to pipeline/runner.py.

    Integration
    ───────────
    pipeline_log.pipeline_start(task_context.task_id, config.initializer, len(task_context.orders))
    t0 = pipeline_log.stage_start("clarke_wright")
    solutions = initializer(task_context, config.initializer_config)
    pipeline_log.stage_done("clarke_wright", len(solutions), t0)
    pipeline_log.evaluation_start(len(solutions))
    # ... evaluate ...
    pipeline_log.pipeline_summary(run_result)
    """

    _log = get_logger("pipeline")

    def pipeline_start(
            self,
            task_id: str,
            pipeline_name: str,
            n_orders: int,
    ) -> None:
        console.rule(
            f"[bold cyan]Pipeline: {pipeline_name}[/]"
            f"   task=[bold]{task_id}[/]"
            f"   orders=[bold]{n_orders}[/]"
        )

    def stage_start(self, stage: str, n_inputs: int = 0) -> float:
        label = f"  (n_inputs={n_inputs})" if n_inputs else ""
        self._log.info(f"  ▶ [stage]{stage}[/]{label}")
        return time.perf_counter()

    def stage_done(self, stage: str, n_outputs: int, t0: float) -> None:
        elapsed = time.perf_counter() - t0
        self._log.info(
            f"  ✓ [stage]{stage}[/] → "
            f"[bold]{n_outputs}[/] solutions  [dim]({elapsed:.2f}s)[/]"
        )

    def evaluation_start(self, n_solutions: int) -> None:
        self._log.info(f"  ◎ Evaluating [bold]{n_solutions}[/] solutions…")

    def solution_evaluated(
            self,
            solution_id: str,
            fitness: float,
            is_valid: bool,
    ) -> None:
        """DEBUG-level per-solution line."""
        color = _fitness_style(fitness)
        badge = "✓" if is_valid else "✗"
        badge_color = "green" if is_valid else "red"
        self._log.debug(
            f"    [{badge_color}]{badge}[/] {solution_id}: [{color}]{fitness:.3f}[/]"
        )

    def pipeline_summary(self, run_result: Any) -> None:
        """
        Prints a rich table of all evaluated solutions from a PipelineRunResult.

        run_result must have:
          .task_id, .pipeline_name, .solutions (list of Solution with .metrics),
          .summary dict with keys: total_solutions, valid_solutions,
                                   best_fitness_score, best_solution_id
        """
        summary   = run_result.summary
        solutions = run_result.solutions

        tbl = Table(
            title=(
                f"[bold]Results — task=[cyan]{run_result.task_id}[/]  "
                f"pipeline=[cyan]{run_result.pipeline_name}[/][/]"
            ),
            box=box.ROUNDED,
            show_lines=False,
            header_style="bold dim",
        )
        tbl.add_column("solution_id",  overflow="fold", max_width=36)
        tbl.add_column("valid",        justify="center", width=7)
        tbl.add_column("fitness",      justify="right")
        tbl.add_column("trips",        justify="right")
        tbl.add_column("orders",       justify="right")
        tbl.add_column("dist km",      justify="right")
        tbl.add_column("late",         justify="right")
        tbl.add_column("p_hard",       justify="right", style="red")
        tbl.add_column("p_dir",        justify="right", style="yellow")

        for sol in solutions[:25]:
            m = sol.metrics
            color = _fitness_style(m.fitness_score)
            tbl.add_row(
                f"[dim]{sol.solution_id}[/]",
                "[green]✓[/]" if m.is_valid else "[red]✗[/]",
                f"[{color}]{m.fitness_score:.3f}[/]",
                str(m.trip_count),
                str(m.total_orders),
                f"{m.total_distance_km:.1f}",
                str(m.late_orders_count),
                f"{m.p_hard:.2f}",
                f"{m.p_direction:.2f}",
            )

        if len(solutions) > 25:
            tbl.add_row(f"  … {len(solutions) - 25} more …", *[""] * 8)

        console.print(tbl)

        best_f = summary.get("best_fitness_score")
        best_f_str = f"[bold cyan]{best_f:.3f}[/]" if best_f is not None else "[dim]N/A[/]"
        console.print(
            Panel(
                f"total=[bold]{summary['total_solutions']}[/]   "
                f"valid=[bold green]{summary['valid_solutions']}[/]   "
                f"best_fitness={best_f_str}   "
                f"best_id=[dim]{summary.get('best_solution_id', 'N/A')}[/]",
                title="[bold]Pipeline Summary[/]",
                expand=False,
            )
        )

    @contextmanager
    def timed_stage(self, stage: str, n_inputs: int = 0) -> Iterator[None]:
        """Context-manager that times a stage automatically."""
        t0 = self.stage_start(stage, n_inputs)
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            self._log.info(
                f"  ✓ [stage]{stage}[/] done [dim]({elapsed:.2f}s)[/]"
            )

    @contextmanager
    def solution_evaluation_progress(self, total: int) -> Iterator[Progress]:
        """Live progress bar while evaluating a batch of solutions."""
        with Progress(
                SpinnerColumn(),
                TextColumn("[stage]Evaluating[/]"),
                BarColumn(bar_width=28),
                MofNCompleteColumn(),
                TimeElapsedColumn(),
                console=console,
                transient=True,
        ) as progress:
            task_id = progress.add_task("eval", total=total)
            progress._managed_task = task_id  # type: ignore[attr-defined]
            yield progress


# ─────────────────────────────────────────────────────────────────────────────
# 8. FitnessLogger
# ─────────────────────────────────────────────────────────────────────────────

class FitnessLogger:
    """
    Detailed fitness component breakdowns.

    Integration (pipeline/metrics.py or anywhere evaluate_fitness is called)
    ─────────────────────────────────────────────────────────────────────────
    from logger import fitness_log

    components = evaluate_fitness(solution, task_context)
    fitness_log.fitness_breakdown(solution.solution_id, components)

    # Or just the warnings:
    if not components.is_valid:
        fitness_log.warn_invalid(solution.solution_id, components.p_hard)
    if components.late_orders_count:
        fitness_log.warn_late_orders(solution.solution_id,
                                     components.late_orders_count,
                                     components.total_lateness_minutes)
    """

    _log = get_logger("fitness")

    def fitness_breakdown(self, solution_id: str, components: Any) -> None:
        """
        Full component table for a FitnessComponents (pipeline.fitness)
        or any object with the same attributes.
        """
        tbl = Table(
            title=f"Fitness breakdown — [dim]{solution_id}[/]",
            box=box.SIMPLE_HEAD,
            show_header=True,
            padding=(0, 2),
        )
        tbl.add_column("component",   style="bold",  min_width=22)
        tbl.add_column("value",       justify="right")
        tbl.add_column("note",        style="dim")

        def row(name: str, val: Any, note: str = "") -> tuple:
            return (name, val, note)

        rows = [
            row("is_valid",             str(components.is_valid)),
            row("─── score ───",        ""),
            row("fitness_score",        _fmt(components.fitness_score),          "lower is better"),
            row("t_total_hours",        _fmt(components.t_total_hours),          "travel time"),
            row("─── hard penalties ─", ""),
            row("p_hard",               _fmt(components.p_hard),                 "capacity + mass + SLA"),
            row("  p_capacity",         _fmt(components.p_capacity),             "order-count violations"),
            row("  p_mass",             _fmt(components.p_mass),                 "weight violations"),
            row("  p_sla",              _fmt(components.p_sla),                  "late deliveries"),
            row("─── soft penalties ─", ""),
            row("p_sync",               _fmt(components.p_sync),                 "time-window overlap"),
            row("p_fleet",              _fmt(components.p_fleet),                "fleet size cost"),
            row("p_direction",          _fmt(components.p_direction),            "directional spread"),
            row("─── route stats ────", ""),
            row("total_distance_km",    _fmt(components.total_distance_km),      ""),
            row("trip_count",           str(components.trip_count),              ""),
            row("avg_orders_per_trip",  _fmt(components.avg_orders_per_trip),    ""),
            row("late_orders_count",    str(components.late_orders_count),       ""),
            row("total_lateness_min",   _fmt(components.total_lateness_minutes), ""),
            row("max_lateness_min",     _fmt(components.max_lateness_minutes),   "worst single order"),
        ]

        for name, val, note in rows:
            # separators
            if name.startswith("─"):
                tbl.add_row(f"[dim]{name}[/]", "", note)
                continue
            # colour penalty rows that are non-zero red
            is_penalty = name.startswith("p_") or name.startswith("  p_")
            try:
                is_nonzero = float(val) > 0
            except (ValueError, TypeError):
                is_nonzero = False
            val_str = f"[red]{val}[/]" if (is_penalty and is_nonzero) else val
            tbl.add_row(name, val_str, note)

        console.print(tbl)

    def warn_invalid(self, solution_id: str, p_hard: float) -> None:
        self._log.warning(
            f"Solution [bold]{solution_id}[/] is [badge.invalid] INVALID [/] "
            f"p_hard=[red]{p_hard:.3f}[/]"
        )

    def warn_late_orders(
            self,
            solution_id: str,
            count: int,
            total_lateness_min: float,
    ) -> None:
        self._log.warning(
            f"[bold]{solution_id}[/] has [bold red]{count}[/] late order(s)  "
            f"total lateness=[red]{total_lateness_min:.1f}min[/]"
        )

    def warn_weight_violation(
            self,
            solution_id: str,
            trip_id: int,
            actual_kg: float,
            max_kg: float,
    ) -> None:
        self._log.warning(
            f"[bold]{solution_id}[/] trip {trip_id}: "
            f"weight [red]{actual_kg:.1f}kg[/] > max [bold]{max_kg:.1f}kg[/]"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 9. Singleton instances — import these in your modules
# ─────────────────────────────────────────────────────────────────────────────

ea_log         = EvolutionLogger()
cluster_log    = ClusterLogger()
heuristics_log = HeuristicsLogger()
pipeline_log   = PipelineLogger()
fitness_log    = FitnessLogger()


# ─────────────────────────────────────────────────────────────────────────────
# 10. Convenience: task-level banner used in main.py
# ─────────────────────────────────────────────────────────────────────────────

def log_task_start(task_id: str, n_orders: int, n_warehouses: int) -> None:
    """Print a prominent task header (use in main.py's task loop)."""
    console.print(
        Panel(
            f"task_id=[bold cyan]{task_id}[/]   "
            f"orders=[bold]{n_orders}[/]   "
            f"warehouses=[bold]{n_warehouses}[/]",
            title="[bold magenta]▶ New Task[/]",
            expand=False,
        )
    )


def log_task_done(task_id: str, n_solutions: int) -> None:
    """Print a task completion line."""
    get_logger("main").info(
        f"Task [bold cyan]{task_id}[/] archived "
        f"[bold green]{n_solutions}[/] unique solutions ✓"
    )


def log_master_done(output_path: str, n_tasks: int) -> None:
    """Print the final done banner in main.py."""
    console.print(
        Panel(
            f"[bold]{n_tasks}[/] tasks complete.  "
            f"Output: [bold cyan]{output_path}[/]",
            title="[bold green]All Done ✓[/]",
            expand=False,
        )
    )