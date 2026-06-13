# Simulator Architecture

## Overview
Simulator for retail delivery logistics and Vehicle Routing Problem (VRP) optimization with integrated clustering capabilities.

## System Components

### 1. Core Simulator Engine (`simulator/core.py`)
- **SimulationController**: Main simulation orchestrator
- **TimeManager**: Handles simulation time progression
- **EventManager**: Manages events (orders, vehicle movements, deliveries)
- **StateManager**: Tracks system state at each time step

### 2. Data Schemas (`simulator/schemas/`)

#### Core Entities
- **Order**: Customer delivery orders
  - Order ID, customer location, time windows, demand, priority
  - Status: pending, assigned, in_transit, delivered, cancelled
  
- **Warehouse**: Distribution centers
  - Location, capacity, inventory, operating hours
  - Transport fleet assignment
  
- **Transport**: Delivery transports
  - Transport ID, capacity, current location, route
  - Status: idle, loading, delivering, returning
  
- **Route**: Planned delivery routes
  - Sequence of stops, estimated times, distances
  - Optimized using VRP algorithms
  
- **Customer**: Delivery recipients
  - Location, demand patterns, service constraints

### 3. Utilities (`simulator/utils/`)

## Data Flow

```
Orders Input  →  VRP Solver  →  Route Assignment  →  Simulation
     ↓               ↓                 ↓                 ↓
 Database     Optimized Routes   Vehicle Fleet    Success Verdict
```

## Integration Points

### VRP Solver ↔ Simulator
- VRP generates initial routes at simulation start
- Dynamic re-optimization based on simulation events
- Simulator validates route feasibility

## Technology Stack
- **Language**: Python 3.10+
- **Data Structures**: Pydantic for schema validation

## Development Phases

### Phase 1: Core Schemas
- [x] Implement Order schema
- [x] Implement Warehouse schema
- [x] Implement Agent/Vehicle schema
- [x] Implement Route schema
- [x] Implement Customer schema

### Phase 2: Simulator Engine
- [ ] Implement SimulationController
- [ ] Implement TimeManager
- [ ] Implement EventManager
- [ ] Implement StateManager

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
