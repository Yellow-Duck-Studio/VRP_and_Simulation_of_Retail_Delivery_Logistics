# VRP and Simulation of Retail Delivery Logistics

![CI Status](https://github.com/Yellow-Duck-Studio/VRP_and_Simulation_of_Retail_Delivery_Logistics/actions/workflows/simulator_tests.yml/badge.svg)
![Python Version](https://img.shields.io/badge/python-3.12-blue.svg)

<div align="center">
  <img src="assets/logo.png" alt="Project Logo" width="200"/>
</div>

## Dashboard Preview

<!-- Dashboard Screenshot Placeholder -->
<div align="center">
  <img src="assets/dashboard_overview.png" alt="Dashboard Overview" width="800"/>
</div>

<!-- Simulation Metrics Placeholder -->
<div align="center">
  <img src="assets/simulation_metrics.png" alt="Simulation Metrics" width="800"/>
</div>

## Architecture

The system consists of three main components:

1. **Clustering Module** (`evolutionary_algorithm/`): Groups orders into optimal delivery routes using evolutionary algorithms
2. **Simulation Engine** (`simulator/`): Simulates delivery operations with realistic constraints and events
3. **Frontend Dashboard** (`frontend/`): React-based web interface for visualization and analysis

## Quick Start with Docker

The fastest way to run the entire system is using Docker Compose:

```bash
# Clone the repository
git clone https://github.com/Yellow-Duck-Studio/VRP_and_Simulation_of_Retail_Delivery_Logistics.git
cd VRP_and_Simulation_of_Retail_Delivery_Logistics

# Build and start all services
docker compose up --build

# Access the frontend at http://localhost
# Backend API will be available at http://localhost:3001
```

To stop the services:

```bash
docker compose down
```

## Manual Installation

### Prerequisites

- Python 3.12+
- Node.js 25+
- npm

### Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

### Step 2: Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

## Running Modules Separately

### 1. Clustering Module

Run the evolutionary clustering algorithm to optimize order groupings:

```bash
python main.py DBSCAN

# Available algorithms:
python main.py CLWR
python main.py SWEEP
python main.py DSTR
python main.py RND
```

This will:
- Load orders from `data/orders.csv`
- Load warehouses from `data/warehouses.csv`
- Load transport constraints from `data/transport_types.csv`
- Generate optimized clusters for each task
- Save results to `data/master_clusterizations.json`

### 2. Simulation Module

Run the discrete event simulation with clustered data:

```bash
# Basic simulation with default parameters
python -m simulator.main --input test_data_innopolis.json

# Full simulation with custom parameters
python -m simulator.main \
  --input test_data_innopolis.json \
  --start-time "2024-06-17T09:00:00" \
  --time-step 5 \
  --max-steps 100 \
  --output results.json
```

**Command-line Arguments:**
- `--input`: Path to input JSON file with simulation data
- `--start-time`: Simulation start time in ISO format (default: `2024-06-17T09:00:00`)
- `--time-step`: Time step in minutes (default: `5`)
- `--max-steps`: Maximum number of simulation steps (default: `100`)
- `--output`: Path to output JSON file for results (optional)

### 3. Frontend Dashboard

Start the development server:

```bash
python server.py
cd frontend
npm run dev
```

Access the dashboard at `http://localhost:5173`

For production build:

```bash
cd frontend
npm run build
npm run preview
```

## Input Data Format

### Clustering Module Input

- **orders.csv**: Order data with coordinates, weights, and time windows
- **warehouses.csv**: Warehouse locations and capacities
- **transport_types.csv**: Vehicle types with speed and payload limits

### Simulation Module Input

The simulation expects a JSON file with the following structure:

```json
{
  "warehouses": [...],
  "courier_types": [...],
  "couriers": [...],
  "orders": [...],
  "routes": [...],
  "distance_matrix": {...}
}
```

See `simulator/input_schema.json` for the complete schema definition and `simulator/test_data_innopolis.json` for an example.

## Testing

Run the test suite:

```bash
cd simulator

# Run all tests
pytest

# Run with coverage
pytest --cov=simulator --cov-report=html
```