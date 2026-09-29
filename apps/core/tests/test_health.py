import pytest


@pytest.mark.django_db
def test_health_confirms_db_and_pgvector(api_client):
    """B0's actual gate: not just 'server responds' but 'the database is
    reachable and the vector extension is installed' — a green health check
    that never touched the DB would hide a broken DATABASE_URL."""
    response = api_client.get("/api/health/")
    assert response.status_code == 200
    assert response.data["status"] == "ok"
    assert response.data["pgvector"] == "ok"


def test_health_requires_no_auth(api_client):
    response = api_client.get("/api/health/")
    assert response.status_code != 401
