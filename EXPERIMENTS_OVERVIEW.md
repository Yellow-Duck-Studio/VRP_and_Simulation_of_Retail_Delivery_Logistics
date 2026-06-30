# Experiments Overview

## Purpose

This document explains how the new experiment flow works.

The main goals are:
- run many algorithms without overwriting results
- compare them with one chosen fitness version
- keep Kaggle export as a separate final step


## Main Idea

There are now two different concepts:

1. `experiment runs`
- used for research and comparison
- stored separately
- safe to run many times

2. `published result`
- the single chosen result
- copied into the official output files
- used for Kaggle export


## Two Run Modes

There are now two ways to run algorithms.

### `standalone`

This means:
- run the algorithm by itself
- no evolutionary generations
- good for direct comparison between methods

Examples:
- DBSCAN alone
- Sweep alone
- Clarke-Wright alone
- Destroy & Repair alone

This is now the default mode for `experiment`.

### `evolutionary`

This means:
- run the evolutionary algorithm
- use the selected method as the starting strategy
- generations will appear in the logs

Examples:
- DBSCAN as a seed for evolutionary search
- Clarke-Wright as a seed for evolutionary search
- Random as a seed for evolutionary search

Use this mode only when you explicitly want the evolutionary loop.


## Registered Algorithms

The experiment system currently supports these algorithm names:

- `dbscan`
- `sweep`
- `clarke_wright`
- `destroy_repair`
- `random`

These names are resolved in:
- `experiments/registry.py`


## Fitness Versions

Fitness is now versioned.

Current versions:
- `business_v1`
- `basic_v1`

These are defined in:
- `evolutionary_algorithm/fitness_registry.py`

### `business_v1`

Includes:
- travel time
- capacity penalty
- mass penalty
- SLA penalty
- temporal overlap penalty
- fleet penalty
- directional penalty

### `basic_v1`

A reduced version where:
- `sync_weight = 0`
- `fleet_weight = 0`
- `direction_weight = 0`

This is useful for ablation experiments and debugging.


## Experiment Run Structure

Each experiment run gets its own folder:

`data/runs/<run_id>/`

Inside it:

- `manifest.json`
- `leaderboard.csv`
- `leaderboard.json`
- one folder per algorithm

For each algorithm:

- `master_clusterizations.json`
- `master_clusterizations.csv`

This means many runs can coexist without overwriting each other.


## How To Run One Experiment Suite

Example:

```bash
python main.py experiment --algorithms dbscan sweep clarke_wright destroy_repair random --fitness-version business_v1 --label june_suite
```

What this does:
- runs each listed algorithm
- uses `standalone` mode by default
- uses the same fitness version for all of them
- stores results in a new `data/runs/<run_id>/` folder
- writes a leaderboard


## How To Run With Evolutionary Mode

If you want the old generation-based behavior, run:

```bash
python main.py experiment --algorithms dbscan sweep clarke_wright destroy_repair random --execution-mode evolutionary --fitness-version business_v1 --label june_suite
```

In this mode:
- the evolutionary loop is active
- logs like `Gen 0`, `Gen 100`, and `Best Fitness` will appear


## Leaderboard

The leaderboard is saved in:

- `data/runs/<run_id>/leaderboard.csv`
- `data/runs/<run_id>/leaderboard.json`

It contains, for each algorithm:
- total tasks
- total clusterizations
- valid clusterizations
- best fitness score
- average fitness score
- output file paths


## How To Publish One Chosen Result

Publishing means:
- choose one algorithm result from one run
- copy it into the official output files
- build the Kaggle submission file from it

Example:

```bash
python main.py publish --run-id 20260628_102804 --algorithm clarke_wright
```

This updates:
- `data/master_clusterizations.json`
- `data/master_clusterizations.csv`
- `data/final_submission.csv`


## Kaggle Flow

Kaggle export is preserved.

Important change:
- experiments do not directly overwrite the Kaggle files
- only a published run becomes the official Kaggle candidate

So the new flow is:

1. run many experiments
2. compare leaderboard
3. choose the best run
4. publish that run
5. send the generated `final_submission.csv` to Kaggle


## Legacy Single Run

The old one-shot mode still works.

Examples:

```bash
python main.py DBSCAN
python main.py SWEEP
python main.py CLWR
python main.py DSTR
python main.py RND
```

If you want to force standalone mode:

```bash
python main.py CLWR --execution-mode standalone
python main.py DSTR --execution-mode standalone
```

If you want evolutionary mode:

```bash
python main.py CLWR --execution-mode evolutionary
python main.py RND --execution-mode evolutionary
```

This directly writes to:
- `data/master_clusterizations.json`
- `data/master_clusterizations.csv`

So this mode is simpler, but it does not preserve multiple experiment outputs.


## Recommended Workflow

For research:

1. use `experiment`
2. compare leaderboard
3. inspect the best runs
4. publish one selected run

For quick manual checks:

1. use single-run mode




## Important Files

- `main.py`
- `experiments/runner.py`
- `experiments/publish.py`
- `experiments/registry.py`
- `experiments/types.py`
- `evolutionary_algorithm/fitness_registry.py`
- `submission.py`
