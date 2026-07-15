import asyncio
import glob
import re
import subprocess
import json
import os
import traceback

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

ALGO_MAPPING = {
    "DBScan": "DBSCAN",
    "Clarke Wright": "CLWR",
    "Sweep": "SWEEP",
    "Destroy & Repair": "DSTR",
    "Random": "RnD"
}

STANDALONE_ALGORITHMS = ["GNN"]

DATASET_PATHS = {
    "small": {"orders": "./data/small/orders.csv", "warehouses": "./data/small/warehouses.csv"},
    "large": {"orders": "./data/large/orders.csv", "warehouses": "./data/large/warehouses.csv"},
    "big": {"orders": "./data/big/orders.csv", "warehouses": "./data/big/warehouses.csv"}
}


PREDICTIONS_DIR = "data"

# GNN and the evolutionary (main.py) algorithms write their results to two
# separate, dedicated files. Previously the websocket handler pointed GNN's
# subprocess at "./data/predictions" but then unconditionally read back
# "data/master_clusterizations.json" (the evolutionary-algorithms file) for
# every algorithm, including GNN. That meant a GNN run either crashed with
# "file not found" on a fresh checkout, or silently returned a stale
# leftover result from whatever evolutionary algorithm last wrote that file.
# Keeping the paths distinct, and always reading back the exact path each
# algorithm was told to write to, removes that whole class of bug.
CLUSTERING_RESULT_PATH = os.path.join("data", "master_clusterizations.json")
GNN_RESULT_PATH = os.path.join("data", "gnn_master_result.json")


def result_path_for_algorithm(alg: str) -> str:
    return GNN_RESULT_PATH if alg in STANDALONE_ALGORITHMS else CLUSTERING_RESULT_PATH

# Каноничные имена алгоритмов для UI. Если имя файла не совпадает ни с одним
# ключом — используем Title Case как fallback, так что новые алгоритмы не
# ломают парсинг.
ALGORITHM_DISPLAY_NAMES = {
    "DBSCAN": "DBSCAN",
    "CLARKE WRIGHT": "Clarke Wright",
    "SWEEP": "Sweep",
    "DESTROY REPAIR": "Destroy & Repair",
    "RND": "Random",
    "RANDOM": "Random",
}


def parse_prediction_filename(filename: str) -> dict:
    """
    "predictions_clarke_wright.json"  -> algorithm="Clarke Wright", eps=None
    "predictions_dbscan_eps_0.1.json" -> algorithm="DBSCAN", eps=0.1
    """
    base = filename
    if base.startswith("predictions_"):
        base = base[len("predictions_"):]
    if base.endswith(".json"):
        base = base[: -len(".json")]

    eps = None
    eps_match = re.search(r"_eps_([\d.]+)$", base)
    if eps_match:
        try:
            eps = float(eps_match.group(1))
        except ValueError:
            eps = None
        base = base[: eps_match.start()]

    algo_key = base.replace("_", " ").strip().upper()
    display = ALGORITHM_DISPLAY_NAMES.get(algo_key, base.replace("_", " ").title())

    label = f"GNN - {display}"
    if eps is not None:
        label += f" (eps={eps:g})"

    return {"algorithm": display, "eps": eps, "label": label}


class ClusterRequest(BaseModel):
    algorithms: List[str]
    dataset: Optional[str] = "small"


@app.post("/api/cluster")
async def run_clustering(request: ClusterRequest):
    results = {}
    paths = DATASET_PATHS.get(request.dataset, DATASET_PATHS["small"])

    env = {
        **os.environ,
        "DATASET_ORDERS": paths["orders"],
        "DATASET_WAREHOUSES": paths["warehouses"]
    }

    try:
        for alg in request.algorithms:
            py_alg_name = ALGO_MAPPING.get(alg)
            if not py_alg_name and alg not in STANDALONE_ALGORITHMS:
                raise HTTPException(status_code=400, detail=f"Unknown algorithm: {alg}")

            if alg == STANDALONE_ALGORITHMS[0]:
                cmd = [
                    "python3", "GNN/predict.py",
                    "--warehouses", paths["warehouses"],
                    "--orders", paths["orders"],
                    "--transport", "./data/transport_types.csv",
                    "--model", "./GNN/model.pt",
                    "--out-prefix", GNN_RESULT_PATH.replace(".json", "")
                ]
                subprocess.run(cmd, check=True, env=env)
            else:
                subprocess.run(["python3", "main.py", py_alg_name], check=True, env=env)

            # For GNN, don't read back the result file since it generates multiple algorithm-specific files
            # The frontend will load specific algorithm results via /api/gnn/{algorithm}
            if alg not in STANDALONE_ALGORITHMS:
                output_path = result_path_for_algorithm(alg)
                with open(output_path, "r", encoding="utf-8") as f:
                    results[alg] = json.load(f)
            else:
                # Return empty result for GNN - frontend loads algorithm-specific data separately
                results[alg] = []

        return results
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/cluster")
async def run_clustering_ws(websocket: WebSocket):
    await websocket.accept()

    try:
        payload = await websocket.receive_json()
        algorithms = payload.get("algorithms", [])
        dataset = payload.get("dataset")

        if not algorithms:
            await websocket.send_json({"type": "error", "message": "No algorithms selected"})
            await websocket.close()
            return

        results = {}
        paths = DATASET_PATHS.get(dataset, DATASET_PATHS["small"])

        env = {
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "DATASET_ORDERS": paths["orders"],
            "DATASET_WAREHOUSES": paths["warehouses"]
        }

        for alg in algorithms:
            py_alg_name = ALGO_MAPPING.get(alg)
            if not py_alg_name and alg not in STANDALONE_ALGORITHMS:
                await websocket.send_json({
                    "type": "error",
                    "algorithm": alg,
                    "message": f"Unknown algorithm: {alg}",
                })
                await websocket.close()
                return

            await websocket.send_json({"type": "algo_start", "algorithm": alg})

            if alg == STANDALONE_ALGORITHMS[0]:
                cmd = [
                    "python3", "-u", "GNN/predict.py",
                    "--warehouses", paths["warehouses"],
                    "--orders", paths["orders"],
                    "--transport", "./data/transport_types.csv",
                    "--model", "./GNN/model.pt",
                    "--out-prefix", GNN_RESULT_PATH.replace(".json", ""),
                ]
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )
            else:
                process = await asyncio.create_subprocess_exec(
                    "python3", "-u", "main.py", py_alg_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    env=env,
                )

            assert process.stdout is not None
            while True:
                raw_line = await process.stdout.readline()
                if not raw_line:
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n").rstrip("\r")
                if line.strip():
                    await websocket.send_json({"type": "log", "algorithm": alg, "line": line})

            returncode = await process.wait()

            if returncode != 0:
                await websocket.send_json({
                    "type": "error",
                    "algorithm": alg,
                    "message": f"'{py_alg_name or alg}' exited with code {returncode}",
                })
                await websocket.close()
                return

            # For GNN, don't read back the result file since it generates multiple algorithm-specific files
            # The frontend will load specific algorithm results via /api/gnn/{algorithm}
            if alg not in STANDALONE_ALGORITHMS:
                output_path = result_path_for_algorithm(alg)
                with open(output_path, "r", encoding="utf-8") as f:
                    alg_data = json.load(f)
                results[alg] = alg_data
                await websocket.send_json({"type": "algo_done", "algorithm": alg, "data": alg_data})
            else:
                # Return empty result for GNN - frontend loads algorithm-specific data separately
                results[alg] = []
                await websocket.send_json({"type": "algo_done", "algorithm": alg, "data": []})

        await websocket.send_json({"type": "done", "results": results})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        traceback.print_exc()
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/api/predictions/list")
async def list_prediction_files():
    pattern = os.path.join(PREDICTIONS_DIR, "predictions_*.json")
    files = sorted(glob.glob(pattern))

    manifest = []
    for path in files:
        filename = os.path.basename(path)
        meta = parse_prediction_filename(filename)
        manifest.append({"filename": filename, **meta})

    manifest.sort(key=lambda m: (m["algorithm"], m["eps"] if m["eps"] is not None else -1))

    return {"files": manifest}


class PredictionsBatchRequest(BaseModel):
    filenames: List[str]


@app.post("/api/predictions/batch")
async def load_prediction_files_batch(request: PredictionsBatchRequest):
    result = {}
    for filename in request.filenames:
        safe_name = os.path.basename(filename)
        path = os.path.join(PREDICTIONS_DIR, safe_name)

        if not os.path.isfile(path):
            result[safe_name] = {"error": "File not found"}
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                result[safe_name] = json.load(f)
        except Exception as e:
            result[safe_name] = {"error": str(e)}

    return result


@app.get("/api/gnn/{algorithm}")
async def load_gnn_algorithm_result(algorithm: str):
    """
    Load a specific GNN algorithm result file generated by predict.py.
    gnn_master_result_{algorithm}.json
    """
    safe_algo = algorithm.replace("..", "").replace("/", "").replace("\\", "")
    filename = f"gnn_master_result_{safe_algo}.json"
    path = os.path.join(PREDICTIONS_DIR, filename)

    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"GNN result file not found: {filename}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SimulationConfig(BaseModel):
    input: Optional[str] = "test_data_innopolis.json"
    time_step: Optional[int] = 5
    max_steps: Optional[int] = 100
    strict: Optional[bool] = False


@app.get("/api/simulate/inputs")
async def list_simulation_inputs():
    pattern = os.path.join("simulator", "test_data*.json")
    files = sorted(os.path.basename(p) for p in glob.glob(pattern))
    if not files:
        files = ["test_data_innopolis.json"]
    return {"inputs": files}


@app.post("/api/simulate")
async def run_simulation(config: SimulationConfig = SimulationConfig()):
    args = [
        "python3", "-m", "simulator.main",
        "--input", config.input or "test_data_innopolis.json",
        "--time-step", str(config.time_step or 5),
        "--max-steps", str(config.max_steps or 100),
    ]
    if config.strict:
        args.append("--strict")

    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=True,
            cwd="simulator"
        )
        return PlainTextResponse(result.stdout)
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip() or (e.stdout or "").strip() or f"Simulation exited with code {e.returncode}"
        raise HTTPException(status_code=500, detail=detail)


app.mount("/data", StaticFiles(directory="data"), name="data")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=3001)