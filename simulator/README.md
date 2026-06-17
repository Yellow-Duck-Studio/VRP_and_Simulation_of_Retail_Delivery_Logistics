# VRP and Retail Delivery Logistics Simulator

A Python-based simulator for retail delivery logistics and Vehicle Routing Problem (VRP) optimization.

## Overview

This simulator models the complete delivery logistics workflow including:
- Order management with time windows and priorities
- Warehouse and distribution center operations
- Courier fleet management with different vehicle types
- Route planning and optimization
- Simulation of delivery operations

## Key Components

- **SimulationController**: Main orchestrator that manages the simulation lifecycle
- **TimeManager**: Handles time progression with configurable time steps
- **EventManager**: Tracks and publishes simulation events (orders, deliveries, vehicle movements)
- **StateManager**: Maintains system state including orders, warehouses, couriers, and routes
- **Data Schemas**: Pydantic-based models for orders, warehouses, couriers, and routes

## How It Works

1. Load simulation data from a JSON file containing warehouses, courier types, couriers, orders, and routes
2. Initialize the simulation controller with start time and time step parameters
3. Run the simulation step-by-step, processing events and updating system state
4. Track metrics including delivery rates, SLA compliance, and courier utilization
5. Export results to JSON for analysis

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

### Command-Line Arguments

- `--input`: Path to input JSON file with simulation data (default: `test_data_innopolis.json`)
- `--start-time`: Simulation start time in ISO format (default: `2024-06-17T09:00:00`)
- `--time-step`: Time step in minutes (default: `5`)
- `--max-steps`: Maximum number of simulation steps (default: `100`)
- `--output`: Path to output JSON file for results (optional)

### Example

```bash
python3 -m simulator.main \
  --input simulator/test_data_innopolis.json \
  --start-time "2024-06-17T09:00:00" \
  --time-step 5 \
  --max-steps 100 \
  --output results.json
```

## Input Data Format

The input JSON scheme file is defined in `simulator/schemas/input_schema.json`.

The input JSON file should contain:
- `warehouses`: Distribution centers with locations
- `courier_types`: Vehicle types with capacity and speed specifications
- `couriers`: Fleet of delivery vehicles
- `orders`: Customer delivery orders with time windows
- `routes`: Pre-planned delivery routes (optional)
- `distance_matrix`: Travel distances between locations

See `simulator/test_data_innopolis.json` for a complete example.

## Output

The simulator prints:
- Initial state summary (warehouses, couriers, orders)
- Simulation progress
- Final metrics (delivery rate, SLA hit rate, courier utilization)
- Event summary by type

If `--output` is specified, results are saved to JSON including metrics, event log, and final state.

## Development Status

- [x] Core data schemas (Order, Warehouse, Courier, Route, CourierType)
- [x] Basic simulation engine (TimeManager, EventManager, StateManager)
- [ ] VRP solver integration
- [ ] Analytics and reporting
- [ ] Connection with external services

## Architecture

See `simulator/ARCHITECTURE.md` for detailed system architecture and component descriptions.