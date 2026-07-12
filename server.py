import asyncio
import glob
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
                subprocess.run([
                    "python3", "GNN/predict.py",
                    "--warehouses", paths["warehouses"],
                    "--orders", paths["orders"],
                    "--transport", "./data/transport_types.csv",
                    "--model", "./GNN/model.pt",
                    "--out", "data/master_clusterizations.json"
                ], check=True, env=env)
            else:
                subprocess.run(["python3", "main.py", py_alg_name], check=True, env=env)

            output_path = os.path.join("data", "master_clusterizations.json")
            with open(output_path, "r", encoding="utf-8") as f:
                results[alg] = json.load(f)

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
                process = await asyncio.create_subprocess_exec(
                    "python3", "-u", "GNN/predict.py",
                    "--warehouses", paths["warehouses"],
                    "--orders", paths["orders"],
                    "--transport", "./data/transport_types.csv",
                    "--model", "./GNN/model.pt",
                    "--out", "./data/master_clusterizations.json",
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

            output_path = os.path.join("data", "master_clusterizations.json")
            with open(output_path, "r", encoding="utf-8") as f:
                alg_data = json.load(f)

            results[alg] = alg_data
            await websocket.send_json({"type": "algo_done", "algorithm": alg, "data": alg_data})

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