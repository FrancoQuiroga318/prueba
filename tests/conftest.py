import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    monkeypatch.setenv("SO_DB_PATH", str(path))
    return path


@pytest.fixture
def client(db_path):
    from app.main import app

    with TestClient(app) as c:  # el "with" ejecuta el arranque (crea las tablas)
        yield c
