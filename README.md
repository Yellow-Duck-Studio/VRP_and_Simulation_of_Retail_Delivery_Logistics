# VRP_and_Simulation_of_Retail_Delivery_Logistics

## About the Project
Managing retail delivery logistics involves complex mathematical routing and precise cost calculations. Current systems often struggle with inefficient route validation, leading to financial losses in courier payouts. 

Built for the Industrial track, this project addresses this gap by providing an automated VRP (Vehicle Routing Problem) simulator. Our solution evaluates delivery efficiency against a baseline using advanced algorithms to provide actionable financial and logistical analytics.

The system is divided into two core components:
1. **Clustering Module:** Automates the optimal grouping of delivery orders using DBSCAN and Evolutionary algorithms.
2. **Simulation Module:** Validates VRP solutions and precisely calculates courier compensation based on simulated outcomes.

## Development Roadmap

**MVP 0: Core Architecture & Data Ingestion (Current Scope)**
* Parsing and ingestion of raw simulation datasets.
* Initial cluster generation using DBSCAN.
* Implementation of an Evolutionary algorithm for optimal cluster configuration.
* Structured output generation of final clustering results.
* Foundational system flow with basic validation placeholders and data-reading tests.

**MVP 1: Functional Validation**
* Full implementation of VRP constraint validation logic.
* Comprehensive unit and integration testing pipelines for validation verdicts.

**MVP 2: Analytics & Refinement**
* Refinement of core simulation mechanics.
* Introduction of logistics analytics, specifically courier payment calculations.
* Integration testing for analytical outputs.

**Out of Scope (Postponed)**
* Clarke-Wright algorithm for baseline initial splitting.
* Destroy & Repair algorithms for advanced local optimization.
* Integration with external customer services.

## Technical Stack
* **Python:** Core backend language for rapid prototyping and robust logic.
* **NumPy:** C++ backed processing for high-speed mathematical array operations crucial to VRP calculations.
* **scikit-learn:** Reliable pre-built algorithms (DBSCAN) and mathematical metrics.
* **Pandas:** Efficient manipulation and parsing of initial raw datasets.
* **Pydantic:** Strict object creation and data validation within the simulation module.
* **pytest:** Primary framework for all unit and integration testing.
