import json
import subprocess
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from server import app


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------

@pytest.fixture
def client():
    """Test client for the FastAPI app."""
    return TestClient(app)


# ----------------------------------------------------------------------
# Tests for /api/cluster (POST)
# ----------------------------------------------------------------------

def test_cluster_post_success(client):
    """POST /api/cluster runs algorithms and returns combined results."""
    dummy_results = {"clusters": [[1, 2], [3, 4]]}

    with patch("subprocess.run") as mock_run, \
         patch("builtins.open", new_callable=MagicMock) as mock_open:

        mock_run.return_value = MagicMock(returncode=0)

        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = json.dumps(dummy_results)
        mock_open.return_value = mock_file

        response = client.post("/api/cluster", json={"algorithms": ["DBScan"]})
        assert response.status_code == 200
        assert response.json() == {"DBScan": {"clusters": [[1, 2], [3, 4]]}}

        mock_run.assert_called_once_with(
            ["python3", "main.py", "DBSCAN"],
            check=True
        )


def test_cluster_post_invalid_algorithm(client):
    response = client.post("/api/cluster", json={"algorithms": ["UnknownAlg"]})
    assert response.status_code == 400
    assert "Unknown algorithm" in response.json()["detail"]


def test_cluster_post_subprocess_failure(client):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, "python3")
        response = client.post("/api/cluster", json={"algorithms": ["DBScan"]})
        assert response.status_code == 500
        assert "non-zero" in response.json()["detail"].lower()


# ----------------------------------------------------------------------
# Helper for WebSocket mocks (no async generator with return)
# ----------------------------------------------------------------------

class MockReadline:
    """Async callable that returns lines sequentially, then b'' at EOF."""
    def __init__(self, lines):
        self.lines = lines
        self.index = 0

    async def __call__(self):
        if self.index < len(self.lines):
            line = self.lines[self.index]
            self.index += 1
            return line.encode()
        return b""  # EOF


# ----------------------------------------------------------------------
# Tests for /ws/cluster (WebSocket)
# ----------------------------------------------------------------------

def test_ws_cluster_success(client):
    """WebSocket /ws/cluster streams progress and returns results."""
    dummy_alg_data = {"clusters": [[10, 20]]}
    dummy_results = {"DBScan": dummy_alg_data}

    async def mock_subprocess_exec(*args, **kwargs):
        mock_proc = MagicMock()
        # Simulate stdout.readline returning two log lines then EOF
        mock_proc.stdout.readline = AsyncMock(
            side_effect=[b"Gen 1: best=42\n", b"Gen 2: best=41\n", b""]
        )
        mock_proc.wait = AsyncMock(return_value=0)
        return mock_proc

    with patch("server.asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec), \
         patch("builtins.open", new_callable=MagicMock) as mock_open:

        mock_file = MagicMock()
        mock_file.__enter__.return_value.read.return_value = json.dumps(dummy_alg_data)
        mock_open.return_value = mock_file

        with client.websocket_connect("/ws/cluster") as websocket:
            websocket.send_json({"algorithms": ["DBScan"]})

            msg = websocket.receive_json()
            assert msg["type"] == "algo_start"
            assert msg["algorithm"] == "DBScan"

            msg = websocket.receive_json()
            assert msg["type"] == "log"
            assert "Gen 1" in msg["line"]

            msg = websocket.receive_json()
            assert msg["type"] == "log"
            assert "Gen 2" in msg["line"]

            msg = websocket.receive_json()
            assert msg["type"] == "algo_done"
            assert msg["algorithm"] == "DBScan"
            assert msg["data"] == dummy_alg_data

            msg = websocket.receive_json()
            assert msg["type"] == "done"
            assert msg["results"] == dummy_results


def test_ws_cluster_invalid_algorithm(client):
    with client.websocket_connect("/ws/cluster") as websocket:
        websocket.send_json({"algorithms": ["BadAlg"]})
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "Unknown algorithm" in msg["message"]


def test_ws_cluster_subprocess_failure(client):
    async def mock_subprocess_exec(*args, **kwargs):
        mock_proc = MagicMock()
        mock_proc.stdout.readline = AsyncMock(return_value=b"")
        mock_proc.wait = AsyncMock(return_value=1)
        return mock_proc

    with patch("server.asyncio.create_subprocess_exec", side_effect=mock_subprocess_exec):
        with client.websocket_connect("/ws/cluster") as websocket:
            websocket.send_json({"algorithms": ["DBScan"]})
            msg = websocket.receive_json()
            assert msg["type"] == "algo_start"
            msg = websocket.receive_json()
            assert msg["type"] == "error"
            assert "exited with code 1" in msg["message"]


def test_ws_cluster_no_algorithms(client):
    with client.websocket_connect("/ws/cluster") as websocket:
        websocket.send_json({"algorithms": []})
        msg = websocket.receive_json()
        assert msg["type"] == "error"
        assert "No algorithms selected" in msg["message"]


# ----------------------------------------------------------------------
# Tests for /api/simulate (POST)
# ----------------------------------------------------------------------

def test_simulate_success(client):
    dummy_output = "Simulation completed successfully\nFleet mileage: 1234 km"
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout=dummy_output, stderr="")
        response = client.post("/api/simulate")
        assert response.status_code == 200
        assert response.text == dummy_output
        mock_run.assert_called_once_with(
            ["python3", "-m", "simulator.main"],
            capture_output=True,
            text=True,
            check=True,
            cwd="simulator"
        )


def test_simulate_failure(client):
    with patch("subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "python3", stderr="Simulation crashed"
        )
        response = client.post("/api/simulate")
        assert response.status_code == 500
        assert "Simulation crashed" in response.text