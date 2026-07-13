# Simulator Architecture

## Overview
Simulator for retail delivery logistics and Vehicle Routing Problem (VRP) optimization.

## System Components

### 1. Core Simulator Engine (`simulator/core.py`)
- **SimulationController**: Main simulation orchestrator; initialises the simulation
- **TimeManager**: Handles simulation time progression
- **EventManager**: Manages events (orders, vehicle movements, deliveries)
- **StateManager**: Tracks system state at each time step

### 2. Data Schemas (`simulator/schemas/`)

#### Core Entities
- **Order**: Delivery orders
  - `order_id`, `warehouse_id`, `delivery_location`, `delivery_time_window` (when should be delivered), `mass_kg`, 
    `ready_time`  
  - Status: `pending`, `assigned`, `in_transit`, `delivered`, `cancelled`
  
- **Warehouse**: Distribution centers
  - `warehouse_id`, `location` (coordinates)
  
- **Courier**: Delivery couriers
  - `courier_id`, `courier_type_id`, `affiliation` (e.g., shift or exchange), `current_location`, `current_load`, 
    `current_route_id` 
    (path from current location to the goal), `planned_route_ids` (list of routes)  
  - Status: `idle`, `loading`, `delivering`, `returning`
  
- **Route**: Planned delivery routes
  - `route_id`, `courier_id`, `warehouse_id`, `start_location`, `end_location`, `start_time`, `status` (planned 
    / in progress / completed), `stops` (list of RouteStop)
  - Optimised by the VRP solver; may be re‑planned dynamically.
  - `end_time`, `total_distance_km`, `total_duration_minutes` are computed by the simulator during execution.
  
- **Courier Type**: Type of courier
  - `type_id`, `name`, `capacity_kg`, `speed_kmh`
  
- **Distance matrix**: Travel distance between locations
  - Tuple of distances of travel distances between all relevant locations

## Data Flow

```
Input JSON → Schema Validation → State Initialization → Simulation Loop
     ↓               ↓                  ↓                    ↓
 Warehouses      Orders           Couriers           Events (step)
 Couriers        Routes           Time               Metrics
```

## Integration Points

### VRP Solver ↔ Simulator
- VRP generates initial routes at simulation start
- Dynamic re-optimization based on simulation events
- Simulator validates route feasibility

## Technology Stack
- **Language**: Python 3.10+
- **Data Structures**: Pydantic for schema validation
- **Testing**: pytest (unit & integration)

## Development Phases

### Phase 1: Core Schemas
- [x] Implement Order schema
- [x] Implement Warehouse schema
- [x] Implement Agent/Vehicle schema
- [x] Implement Route schema
- [x] Implement Courier Type schema

### Phase 2: Simulator Engine
- [x] Implement SimulationController
- [x] Implement TimeManager
- [x] Implement EventManager
- [x] Implement StateManager

### Phase 3: VRP Solver
- [ ] Implement basic CVRP solver
- [ ] Implement VRPTW solver
- [ ] Implement dynamic re-optimization
- [ ] Implement heuristic engines

### Phase 4: Integration & Testing
- [ ] Integrate all modules
- [ ] Add unit tests
- [ ] Add integration tests
- [ ] Performance optimization
