import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_health_returns_200_and_json_status(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_requires_no_auth(client: TestClient) -> None:
    # No Authorization header is sent; endpoint must still succeed.
    response = client.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()
