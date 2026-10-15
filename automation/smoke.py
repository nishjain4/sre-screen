"""Exercise real FastAPI startup, health, and teardown in offline mode."""
from fastapi.testclient import TestClient

from app.main import create_app


with TestClient(create_app()) as client:
    response = client.get("/api/health")
    response.raise_for_status()
    assert response.json()["status"] == "ok", response.text
    print("Application startup, /api/health, and shutdown passed")