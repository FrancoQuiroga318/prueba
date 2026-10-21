"""Arranca el servidor real con Uvicorn y comprueba que el progreso sobrevive a un reinicio."""

import os
import socket
import subprocess
import sys
import time

import httpx

from app.database import BASE_DIR


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(db_path, port):
    env = {**os.environ, "SO_DB_PATH": str(db_path)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        cwd=BASE_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(url + "/").status_code == 200:
                return proc, url
        except httpx.TransportError:
            pass
        time.sleep(0.1)
    proc.terminate()
    raise RuntimeError("El servidor no arrancó")


def stop_server(proc):
    proc.terminate()
    proc.wait(timeout=10)


def test_server_starts_and_progress_persists_after_restart(tmp_path):
    db_path = tmp_path / "persist.db"
    port = free_port()

    proc, url = start_server(db_path, port)
    try:
        q = httpx.get(url + "/api/questions", params={"unit_id": "u5"}).json()[0]
        r = httpx.post(url + "/api/answers", json={"question_id": q["id"], "result": "no"})
        assert r.status_code == 200
    finally:
        stop_server(proc)

    proc, url = start_server(db_path, port)
    try:
        stats = httpx.get(url + "/api/stats").json()
        assert stats["answers"]["total"] == 1
        assert stats["totals"]["studied"] == 1
        assert q["id"] in [x["id"] for x in httpx.get(url + "/api/review").json()]
    finally:
        stop_server(proc)
