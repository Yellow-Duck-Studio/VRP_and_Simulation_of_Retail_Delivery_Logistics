# Simulator Architecture

## Overview

The simulator models retail delivery logistics, including order management, courier fleet operations, route execution, and payment calculation. It is designed to be modular, testable, and extensible for future VRP solver integration and dynamic re‑optimisation.

## System Components

### 1. Core Simulator Engine (`simulator/engine/`)

- **SimulationController**: Main orchestrator; manages the simulation lifecycle, step‑by‑step execution, and delegates state transitions to FSMs.
- **TimeManager**: Handles simulation time progression (discrete time steps).
- **EventManager**: Pub/Sub event bus; logs events (orders created, courier departed, delivery completed, payment sent, etc.).
- **StateManager**: Single source of truth for all entities (orders, couriers, routes, warehouses, courier types, distance matrix, payment config, and metrics).

### 2. Finite State Machines (`simulator/fsm/`)

- **OrderFSM**: Manages order lifecycle:
  - `PENDING` → `ASSIGNED` (when picked up) → `IN_TRANSIT` (optional) → `DELIVERED` / `CANCELLED`
  - Handles ready‑time checks and event publishing.
- **CourierFSM**: Manages courier route progression:
  - `IDLE` → `DELIVERING` (while executing a route) → `IDLE` (when all routes done)
  - Processes stops sequentially, handles waiting for order readiness, capacity checks, and delivery.
  - Tracks working hours for shift‑based payment.
  - Uses `LocationResolver` to map coordinates to matrix keys.

### 3. Data Schemas (`simulator/schemas/`)

#### Core Entities

- **Order**: 
  - Fields: `order_id`, `warehouse_id`, `delivery_location`, `delivery_time_window`, `mass_kg`, `ready_time`, `status`
  - Status: `pending`, `assigned`, `in_transit`, `delivered`, `cancelled`
- **Warehouse**:
  - `warehouse_id`, `location` (with latitude, longitude, optional address)
- **Courier**:
  - `courier_id`, `courier_type_id`, `affiliation_type` (`shift`, `exchange`, `3pl`), `current_location`, `current_load`, `current_route_id`, `planned_route_ids`, `total_work_hours`, `status`
  - Status: `idle`, `loading`, `delivering`, `returning`
- **Route**:
  - `route_id`, `courier_id`, `warehouse_id`, `start_location`, `end_location`, `start_time`, `end_time`, `total_distance_km`, `total_duration_minutes`, `stops` (list of `RouteStop`)
  - Each stop: `order_id`, `location`, `stop_type` (`pickup`/`delivery`), `sequence_number`, `service_duration_minutes`
- **Courier Type**:
  - `type_id`, `name`, `capacity_kg`, `speed_kmh`
- **DistanceMatrix**:
  - Stores distances between any two location keys (string‑based lookups).
- **Payment Config**:
  - Optional top‑level object with `rate_per_km`, `hourly_rate`, `window_bonus`, `base_fee`, `affiliation_multipliers`.

### 4. Utilities and Helpers

- **PaymentCalculator** (`simulator/utils/payment.py`):
  - Calculates courier payment based on affiliation type, vehicle type, distance, on‑time bonus, and (for shift) hours worked.
  - Configurable via JSON input or defaults.
- **LocationResolver** (`simulator/engine/location_resolver.py`):
  - Maps `Location` objects to distance‑matrix keys; handles coordinate normalisation and caching.
- **Logger** (`simulator/utils/logger.py`):
  - Coloured, configurable logging with support for ANSI and plain output.
  - Log level can be set via environment variable or CLI.
- **Route Validator** (`simulator/engine/route_validator.py`):
  - Static pre‑flight validation of routes (checks order existence, distance matrix coverage, capacity, stop ordering, duplicate orders, and optional time‑window feasibility).
  - Produces a `ValidationReport` with errors and warnings.
- **Reporting** (`simulator/reporting.py`):
  - Generates plain‑text summary reports (total cost, per‑courier payments, order delivery vs deadline).

### 5. Data Loading (`simulator/data_loader.py`)

- Parses the input JSON file, instantiates Pydantic models, and populates the `StateManager`.
- Handles datetime parsing, route stop construction, and distance matrix creation.
- Stores the `payment_config` in `StateManager` for later use.

### 6. Main Entry Point (`simulator/main.py`)

- CLI argument parsing (input file, start time, time step, max steps, output JSON, report file, strict validation, log level).
- Loads data, optionally runs validation, executes simulation, and writes output/report.

## Data Flow

```
Input JSON → Data Loader → StateManager → SimulationController (validates routes) → initialize FSMs → Step loop
                                                                                           │
                                                                                           ▼
                                                                                    OrderFSM / CourierFSM
                                                                                           │
                                                                                           ▼
                                                                                    EventManager / StateManager
                                                                                           │
                                                                                           ▼
                                                                                Results (metrics, events, payments)
```

## Integration Points

### VRP Solver (Future)
- The simulator currently **executes pre‑planned routes** from the input JSON.
- A future VRP solver will generate/update `planned_route_ids` and `stops` before or during simulation.
- The `CourierFSM` will consume these routes without modification.

### Frontend (Current)
- A React‑based frontend (`frontend/`) allows users to select datasets, configure simulation parameters, run simulations, and visualise results.
- The frontend communicates via a backend API that invokes the simulator and streams logs.

## Technology Stack

- **Language**: Python 3.10+
- **Data Validation**: Pydantic v2
- **Testing**: pytest (unit & integration)
- **Logging**: Standard `logging` with custom coloured formatter
- **Frontend**: React + TypeScript (optional, separate module)

## Development Phases

### Phase 1: Core Schemas
- [x] Order, Warehouse, Courier, CourierType, Route, RouteStop, DistanceMatrix

### Phase 2: Simulator Engine
- [x] TimeManager, EventManager, StateManager, SimulationController
- [x] Finite State Machines (OrderFSM, CourierFSM)
- [x] Route validation and LocationResolver
- [x] Payment calculator
- [x] Coloured logging with configurable levels
- [x] Report generation

### Phase 3: Integration & Testing
- [x] Unit tests for schemas, FSMs, payment, validation
- [x] Integration tests for full simulation runs
- [ ] Performance optimization and stress testing

## Module Dependencies

```
 ├── data_loader.py
 ├── engine/
 │   ├── event_manager.py
 │   ├── location_resolver.py
 │   └── route_validator.py
 │   ├── simulation_controller.py
 │   ├── state_manager.py
 │   ├── time_manager.py
 ├── fsm/
 │   ├── courier_fsm.py
 │   └── order_fsm.py
 ├── schemas/
 │   └── courier.py, courier_type.py, distance_matrix.py, order.py, route.py, warehouse.py
 ├── utils/
 │   ├── logger.py
 │   └── payment.py
 ├── tests/
 ├── main.py
 └── input_schema.json
```

## Testing

- Unit tests cover all core components (schemas, FSMs, payment, validation, utilities).
- Integration tests execute full simulations with synthetic data.
- Run with `pytest tests/` from the project root.

## Extending the Simulator

- **Adding a new affiliation type**: Update `PaymentCalculator` and schemas.
- **Adding a new vehicle type**: Update `courier_types` in JSON.
- **Adding new event types**: Extend `EventType` enum and handle them in `EventManager` or FSMs.