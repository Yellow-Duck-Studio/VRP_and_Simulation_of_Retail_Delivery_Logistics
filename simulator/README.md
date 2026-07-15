# VRP and Retail Delivery Logistics Simulator

A Python-based simulator for retail delivery logistics and Vehicle Routing Problem (VRP) optimization.

## Overview

This simulator models the complete delivery logistics workflow including:
- Order management with time windows and priorities
- Warehouse and distribution center operations
- Courier fleet management with different vehicle types
- Route planning and optimization
- Simulation of delivery operations
- Courier payment calculation (shift/exchange/3PL models)
- Pre-flight route validation (teleportation, capacity, missing data)
- Coloured logging with configurable levels
- Plain‑text report generation

## Key Components

- **SimulationController**: Main orchestrator that manages the simulation lifecycle
- **TimeManager**: Handles time progression with configurable time steps
- **EventManager**: Tracks and publishes simulation events (orders, deliveries, vehicle movements)
- **StateManager**: Maintains system state including orders, warehouses, couriers, and routes
- **Data Schemas**: Pydantic-based models for orders, warehouses, couriers, and routes
- **PaymentCalculator**: Configurable payment logic (per‑km, hourly, affiliation multipliers, bonuses)
- **RouteValidator**: Static validation of routes before simulation (capacity, distance matrix, stop ordering)
- **Finite State Machines**: `OrderFSM` and `CourierFSM` manage entity lifecycles cleanly

## How It Works

1. Load simulation data from a JSON file containing warehouses, courier types, couriers, orders, routes, distance matrix, and payment configuration.
2. Validate all routes statically (teleportation, capacity, missing data) – can be strict or permissive.
3. Initialize the simulation controller with start time, time step, and validation settings.
4. Run the simulation step‑by‑step, processing events and updating entity states via FSMs.
5. Track metrics including delivery rates, SLA compliance, courier utilisation, and route validation issues.
6. Export results to JSON and/or generate a plain‑text report.

## Requirements

- Python 3.10+

## Installation

```bash
# Clone the repository
git clone https://github.com/Yellow-Duck-Studio/VRP_and_Simulation_of_Retail_Delivery_Logistics.git
cd VRP_and_Simulation_of_Retail_Delivery_Logistics

# Install dependencies
pip install -r requirements.txt
```

## Usage

Run the simulator from the project root:

```bash
python3 -m simulator.main --input simulator/test_data_innopolis.json
```

### Command‑Line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--input` | Path to input JSON file with simulation data | `test_data_innopolis.json` |
| `--start-time` | Simulation start time (ISO format) | `2024-06-17T09:00:00` |
| `--time-step` | Time step in minutes | `5` |
| `--max-steps` | Maximum number of simulation steps | `100` |
| `--output` | Path to output JSON file for results | `None` |
| `--report` | Path to output plain‑text report file | `report.txt` |
| `--strict` | Fail fast if validation fails | `False` |
| `--log-level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) | `INFO` |

### Examples

**Run with custom settings**:
```bash
python3 -m simulator.main \
  --input data/my_scenario.json \
  --start-time "2024-06-17T09:00:00" \
  --time-step 5 \
  --max-steps 200 \
  --output results.json \
  --report summary.txt \
  --strict \
  --log-level DEBUG
```

**Run with default data and no output files**:
```bash
python3 -m simulator.main
```

## Input Data Format

The input JSON must follow the schema defined in `simulator/schemas/input_schema.json`.

### Required Top‑Level Fields

| Field | Description |
|-------|-------------|
| `courier_types` | List of vehicle types with `type_id`, `name`, `capacity_kg`, `speed_kmh` |
| `warehouses` | List of distribution centers with `warehouse_id` and `location` |
| `orders` | List of customer orders with `order_id`, `warehouse_id`, `delivery_location`, `delivery_time_window`, `mass_kg`, `ready_time` |
| `couriers` | List of couriers with `courier_id`, `courier_type_id`, `affiliation_type` (`shift`, `exchange`, `3pl`), `current_location`, `planned_route_ids` |
| `routes` | Pre‑planned routes with `route_id`, `courier_id`, `warehouse_id`, `start_location`, `end_location`, `stops` (pickup/delivery sequence) |
| `distance_matrix` | Travel distances between all relevant locations (from/to pairs) |

### Optional: `payment_config`

```json
"payment_config": {
  "rate_per_km": { "car": 60.0, "moped": 45.0, "foot": 25.0 },
  "hourly_rate": { "car": 400.0, "moped": 300.0, "foot": 200.0 },
  "window_bonus": 150.0,
  "base_fee": 50.0,
  "affiliation_multipliers": { "shift": 1.0, "exchange": 1.2, "3pl": 0.9 }
}
```

If omitted, sensible defaults are used.

See `simulator/test_data_innopolis.json` for a complete example.

## Output

- **Console logs**: Coloured output with timestamps, log levels, and simulation progress.
- **JSON results** (if `--output` is specified): Contains metrics, event log, final state (orders, couriers).
- **Plain‑text report** (if `--report` is specified): Summarises total cost, per‑courier payments, and delivered orders with actual vs deadline times.

## Route Validation

Before simulation, the system performs static route validation:
- Checks that every stop references an existing order.
- Verifies that distance matrix entries exist for each leg.
- Warns about duplicate order IDs, missing stops, or teleportation.
- Computes total load per route and warns/errors if it exceeds courier capacity.
- Optionally enforces time‑window feasibility.

Use `--strict` to abort on any error.

## Development Status

- [x] Core data schemas (Order, Warehouse, Courier, Route, CourierType)
- [x] Basic simulation engine (TimeManager, EventManager, StateManager)
- [x] Finite State Machines for orders and couriers
- [x] Payment calculator with affiliation/vehicle‑based rates
- [x] Route validation (static pre‑flight checks)
- [x] Coloured logging with configurable levels
- [x] Report generation (plain text)
- [ ] Analytics and dashboard

## Architecture

See `simulator/ARCHITECTURE.md` for detailed system architecture and component descriptions.

## Testing

Run the test suite with:

```bash
pytest tests/
```

Unit and integration tests cover data schemas, FSM logic, payment calculation, and full simulation runs.