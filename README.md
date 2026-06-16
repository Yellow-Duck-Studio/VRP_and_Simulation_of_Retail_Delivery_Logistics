# VRP_and_Simulation_of_Retail_Delivery_Logistics

# Local Setup & Execution Guide

## 1. Prerequisites

Ensure you have Python installed on your system.

Install the project dependencies (NumPy, pandas, scikit-learn, Pydantic, etc.) by running your package manager, for example:

```bash
pip install -r requirements.txt
```

## 2. Data Preparation

Locate the `data/` directory in the root of the project.

Place your input files containing the configurations for warehouses, orders, and types of transport directly into this `data/` folder before running the scripts.

You can find the data by following the link:
https://disk.yandex.ru/d/7LI0uwLGG3cPbw

## 3. Running the Clustering Algorithm

Open your terminal and navigate to the project root directory.

Execute the main script to run the DBSCAN and Evolutionary algorithms:

```bash
python main.py
```

The system will parse the local datasets in the `data/` folder, execute the evolution process, and output the optimized clusterizations.

## 4. Viewing the Visualizations

Once the algorithm has successfully generated the clusters, you can visualize specific results.

Run the visualization script from your terminal:

```bash
python vizual.py
```
or
```bash
python vizual.py <task-number>
```
or
```bash
python vizual.py <task-number> <clusterization-number>
```

Provide the specific task and clusterization number you wish to view (`python vizual.py 1 1000`).
