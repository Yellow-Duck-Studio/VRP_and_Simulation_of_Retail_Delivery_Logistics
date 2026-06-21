import subprocess
import json
import os
import traceback

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List

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
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/simulate")
async def run_simulation():
    try:
        result = subprocess.run(
            ["python3", "-m", "simulator.main"],
            capture_output=True, 
            text=True, 
            check=True,
            cwd="simulator"
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=e.stderr or e.stdout)

app.mount("/data", StaticFiles(directory="data"), name="data")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3001)