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


class ClusterRequest(BaseModel):
    algorithms: List[str]


@app.post("/api/cluster")
async def run_clustering(request: ClusterRequest):
    """Kept for backwards compatibility. Blocks until all algorithms finish
    and returns only the final results — no live progress is reported.
    Prefer the /ws/cluster WebSocket endpoint, which streams progress."""
    results = {}
    try:
        for alg in request.algorithms:
            py_alg_name = ALGO_MAPPING.get(alg)
            if not py_alg_name:
                raise HTTPException(status_code=400, detail=f"Unknown algorithm: {alg}")

            subprocess.run(["python3", "main.py", py_alg_name], check=True)

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
    """Runs the requested algorithms one by one, streaming each subprocess's
    stdout to the client live so the UI can show real-time progress.

    Client sends: {"algorithms": ["DBScan", "Sweep", ...]}

    Server sends a sequence of JSON messages:
      {"type": "algo_start", "algorithm": "DBScan"}
      {"type": "log", "algorithm": "DBScan", "line": "Gen 100 | Best Fitness: ..."}
      {"type": "algo_done", "algorithm": "DBScan", "data": {...}}   # parsed master_clusterizations.json for this algorithm
      {"type": "error", "algorithm": "DBScan"?, "message": "..."}
      {"type": "done", "results": {...}}   # all algorithms' data combined, same shape as the old POST endpoint
    """
    await websocket.accept()

    try:
        payload = await websocket.receive_json()
        algorithms = payload.get("algorithms", [])

        if not algorithms:
            await websocket.send_json({"type": "error", "message": "No algorithms selected"})
            await websocket.close()
            return

        results = {}
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}

        for alg in algorithms:
            py_alg_name = ALGO_MAPPING.get(alg)
            if not py_alg_name:
                await websocket.send_json({
                    "type": "error",
                    "algorithm": alg,
                    "message": f"Unknown algorithm: {alg}",
                })
                await websocket.close()
                return

            await websocket.send_json({"type": "algo_start", "algorithm": alg})

            # "-u" + PYTHONUNBUFFERED ensure main.py's print() output reaches us
            # line-by-line instead of being buffered until the process exits.
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
                    "message": f"'{py_alg_name}' exited with code {returncode}",
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