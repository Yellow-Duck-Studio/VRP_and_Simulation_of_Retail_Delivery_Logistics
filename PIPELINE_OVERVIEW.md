# Clustering Pipeline Overview

## What This Pipeline Does

This pipeline builds and evaluates delivery clusterizations for each `task_id`.

It is modular:
- one algorithm creates an initial solution
- another algorithm can improve it
- one shared fitness function evaluates every result in the same way

This makes it easy to compare combinations such as:
- `clarke_only`
- `clarke_then_destroy_repair`
- `trivial_then_destroy_repair`


## Main Idea

The pipeline has 4 stages:

1. Load task data
2. Build an initial solution
3. Optionally improve that solution
4. Compute fitness and save results


## Current Pipeline Roles

### Initializers

An initializer creates the first full solution.

Currently supported:
- `clarke_wright`
- `trivial`

`clarke_wright`:
- uses the Clarke-Wright savings idea
- builds a structured baseline solution

`trivial`:
- creates a very simple seed
- usually one order per trip
- useful when we want Destroy & Repair to be the main search method


### Improvers

An improver takes one or more existing solutions and tries to make them better.

Currently supported:
- `destroy_repair`

`destroy_repair`:
- removes weak parts of a solution
- rebuilds them
- produces new candidate solutions


### Fitness

Every solution is evaluated with one shared fitness function.

This is important because all pipelines must be compared using the same score.

Current fitness structure:

`Fitness = T_total + P_hard + P_sync + P_fleet + P_direction`

Where:
- `T_total`: total travel time
- `P_hard`: hard constraint penalties
- `P_sync`: penalty for poor overlap of time windows inside a trip
- `P_fleet`: penalty for too many active trips
- `P_direction`: penalty for mixing very different directions inside one trip


## Hard Penalties

`P_hard` contains:
- `P_capacity`: too many orders in one trip
- `P_mass`: trip is too heavy for the transport type
- `P_sla`: delivery is late

Current default weights:
- `capacity_penalty_weight = 1000`
- `mass_penalty_weight = 500`
- `sla_penalty_weight = 100`
- `sync_weight = 50`
- `fleet_weight = 2`
- `direction_weight = 5`


## How Solutions Flow Through The System

For one task, the flow is:

1. Load `orders`, `warehouses`, and `constraints`
2. Create a `TaskContext`
3. Run an initializer
4. If configured, run an improver on the initializer output
5. Compute fitness for every candidate solution
6. Sort solutions by fitness
7. Save results to JSON


## Current Presets

The project currently defines these pipeline presets:

- `clarke_only`
- `clarke_then_destroy_repair`
- `trivial_then_destroy_repair`

These are defined in:
- `experiments/presets.py`


## Project Structure

### `main.py`

Entry point for running the pipeline on all tasks.

### `dataio/`

Responsible for reading CSV files and building task objects.

Important file:
- `dataio/loader.py`

### `pipeline/`

Responsible for orchestration, fitness, evaluation, and serialization.

Important files:
- `pipeline/runner.py`
- `pipeline/fitness.py`
- `pipeline/metrics.py`
- `pipeline/types.py`

### `heuristics/`

Contains the actual clustering logic.

Important files:
- `heuristics/clarke_wright.py`
- `heuristics/destroy_repair.py`
- `heuristics/savings_core.py`
- `heuristics/destroy_repair_core.py`

### `evolutionary_algorithm/`

This is separate legacy work.

It is not part of the new modular pipeline.


## How To Run

Run from the project folder:

```bash
python main.py
```


## Input Data

The pipeline expects data in the shared `data/` directory next to the project folder.

In the current repo layout, that means:

`../data`

Main input files:
- `orders.csv`
- `warehouses.csv`
- `transport_types.csv`


## Output

Results are saved under:

`../data/pipeline_runs`

The output is grouped by preset name and then by task:
- `pipeline_runs/clarke_only/task_1.json`
- `pipeline_runs/clarke_then_destroy_repair/task_1.json`
- `pipeline_runs/trivial_then_destroy_repair/task_1.json`


## Important Note About Validity

A pipeline run can finish successfully even if some solutions are invalid.

This does not mean the code failed.

It means:
- the solution was built
- but its fitness evaluation found violations such as:
- too many orders in one trip
- too much total mass
- late delivery

This is normal for baseline methods and is one reason Destroy & Repair exists.


## Short Summary

The new pipeline separates responsibilities clearly:
- `initializer` builds a starting solution
- `improver` improves it
- `fitness` evaluates it
- `runner` manages the full process

This makes the system easier to compare, extend, and explain.
