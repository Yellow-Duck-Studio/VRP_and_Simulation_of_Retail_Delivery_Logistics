# Exact ILP Solver for Courier Clustering

An **exact** (not heuristic) solver that partitions a warehouse's pending
orders into courier trips (clusters), minimizing total delivery cost while
respecting time windows, vehicle payload limits, and a fleet-size
(courier-availability) constraint.

It is a scaled-up replacement for a bitmask-DP solver, which keeps the
same optimality guarantee but scales further in practice. The complexity
picture, to be precise about it:

- **Stage 1 (candidate enumeration)** is genuinely polynomial in `n` for a
  fixed `max_k`: the number of candidates is
  `Σ_{k=1}^{max_k} C(n, k) · k!`, i.e. `O(n^max_k)`, not `O(2^n)`. This is
  the part that actually removes the exponential blow-up a full bitmask
  DP has (which keeps state for all `2^n` subsets of the warehouse's
  orders, infeasible past roughly n≈20).
- **Stage 2 (the ILP)** is set-partitioning, which is **NP-hard** in
  general — `scipy.optimize.milp`'s branch-and-cut (HiGHS) has no
  polynomial worst-case time guarantee. It scales further than a brute
  bitmask DP in practice because its variable count is the number of
  *candidate clusters* (not `2^n` order-subsets) and because the
  exact-cover / interval-concurrency constraint structure is friendly to
  branch-and-cut — HiGHS routinely solves instances with thousands of
  binary variables in seconds — but this is an empirical/practical
  advantage, not an asymptotic one.

So the honest summary is: stage 1 trades exponential for polynomial
complexity (at the cost of capping cluster size at `max_k`), while stage 2
stays NP-hard in theory but is fast enough in practice for realistic
per-warehouse order counts (~30). There is no overall worst-case
polynomial-time guarantee for the pipeline.

## How it works

### 1. Candidate cluster enumeration (vectorized brute force)

For each warehouse, every subset of orders of size `1..max_k` (default
`max_k=5`) is considered as a candidate cluster. For each subset, every
visiting order (permutation) and every transport type is evaluated to find
the cheapest feasible route — this is the same brute-force cost
computation as a plain bitmask solver would use, but batched with NumPy
across all subsets/permutations/transports at once instead of Python
loops, which is what makes it fast enough at scale.

For each candidate cluster the solver computes:

- **Round-trip distance/cost**, including the return leg from the last
  delivery back to the warehouse (the courier physically has to come
  back — this used to be priced as one-way only, which underpriced
  clusters).
- **`start_epoch` / `finish_epoch`** — the moment the courier leaves the
  warehouse and the moment it is back and free for its next trip.
- **Feasibility** against each order's pickup/deadline time window and the
  transport's payload capacity.
- **Cost**, using the model below.

Only feasible clusters are kept; infeasible ones are discarded.

### 2. Set-partitioning ILP (`scipy.optimize.milp`, HiGHS)

Given all candidate clusters, an integer program selects a subset of them
such that:

- every order is covered **exactly once** (set-partitioning constraint), and
- total cost is minimized.

This is solved exactly with `scipy.optimize.milp` (HiGHS backend, bundled
with SciPy — no external solver or network access needed). It replaces the
`2^n`-state bitmask DP with an ILP formulation of the identical problem,
so the result is still a provable optimum, not an approximation.

### 3. Courier-capacity (fleet size) constraint

Real fleets are finite, especially during peak load. The ILP also enforces
that at most `max_couriers` candidate clusters are ever simultaneously "in
flight" (`start_epoch <= t < finish_epoch`), via one linear constraint per
time breakpoint (sweep-line over distinct start times). A courier that
finishes trip A before trip B starts is free to be reused for trip B — the
constraint caps genuine concurrency, not the total number of trips.

This turns "cheapest partition assuming infinite couriers" into "cheapest
partition achievable by a fixed-size courier fleet."

If the ILP is infeasible with `max_couriers` set, the solver re-solves once
without the courier cap (diagnostics only) and reports how many couriers
*would* have been needed for the cheapest unconstrained partition.

`max_couriers` is sampled uniformly per (task, warehouse) from
`COURIER_M_RANGE` (default `(2, 15)`) when generating training data, so a
downstream model (e.g. a GNN) sees examples across a realistic range of
fleet sizes and can learn to condition on it, rather than fleet size being
an implicit constant baked into one dataset.

## Cost model

For a cluster served by transport `t` with mass `mass_combo`:

```
cost = fixed_fee
     + per_km_fee   * total_round_trip_distance_km
     + per_order_fee * number_of_orders
     + per_kg_min_fee * sum_over_legs(leg_minutes * remaining_mass_kg)
```

The `kg·min` term only charges for mass the courier is *still carrying* on
each leg — remaining mass shrinks after every delivery instead of staying
at the full cluster mass for the whole route.

## Input format

**`orders.csv`**

| column | type | notes |
|---|---|---|
| `task_id` | str | |
| `warehouse_id` | str | |
| `order_id` | str | |
| `order_lat`, `order_lon` | float | |
| `pickup_ready_at` | datetime | |
| `delivery_deadline_at` | datetime | |
| `total_mass_kg` | float | |

**`warehouses.csv`**: `task_id`, `warehouse_id`, `lat`, `lon`.

**`transport_types.csv`**: `code`, `fixed_fee`, `per_km_fee`,
`per_order_fee`, `per_kg_min_fee`, `max_payload_kg`, `approx_speed_kmh`.

ID columns (`task_id`, `warehouse_id`, `order_id`) are forced to `str` on
load, otherwise pandas silently upcasts them to `float64` when it meets a
`NaN` in the column (`"1"` → `1.0`), which corrupts string keys written
into downstream archives.

Datetimes are converted to epoch seconds robustly regardless of the
datetime64 resolution pandas picks (`ns`/`us`/`ms`/`s` differ across
pandas versions and environments).

## Output

Running `main(...)` produces three files (prefixed with `out_prefix`):

- **`{out_prefix}_clusterizations.json`** — full solution per task/warehouse
  (chosen clusters, cost, transport, timing).
- **`{out_prefix}_summary.csv`** — one row per (task, warehouse): order
  count, `max_couriers`, number of clusters, total cost, status
  (`ok` / `infeasible`).
- **`{out_prefix}_master.json`** — a `master_clusterizations.json`-style
  archive, grouped by warehouse (order IDs aren't globally unique across
  warehouses within a task), where each warehouse maps to
  `{"clusters": [...], "max_couriers": M}` so a training pipeline can
  recover the fleet-size constraint the partition was optimized under.

## Usage

```python
from brute_force_ilp import main

results, summary_df = main(
    orders_path="data/orders.csv",
    warehouses_path="data/warehouses.csv",
    transport_path="data/transport_types.csv",
    out_prefix="ilp",
    max_k=5,                 # max cluster size
    courier_m_range=(2, 15), # None disables the courier-capacity constraint
    seed=42,
)
```

Or from the command line (edit the paths at the bottom of the script, or
adapt `if __name__ == "__main__":`):

```bash
python brute_force_ilp.py
```

## Requirements

```
numpy
pandas
scipy   # HiGHS MILP backend is bundled, no external solver needed
```

## Notes & limitations

- Complexity of stage 1 grows combinatorially with `max_k` and orders per
  warehouse; `max_k` caps cluster size to keep enumeration tractable
  (default `5`).
- Solution remains an **exact optimum** for the ILP as formulated — it is
  not a heuristic, subject only to the `max_k` cap on cluster size.
- The concurrency constraint assigns *capacity*, not specific
  courier-to-trip assignments (which would add unnecessary symmetry to the
  ILP); `required_couriers()` can be used standalone to compute the
  minimum number of couriers needed to run any given list of trips.
