"""Tests for the counter service."""

import fakeredis
import pytest


@pytest.fixture(autouse=True)
def mock_redis(monkeypatch):
    """Replace the real Redis client with a fake one for testing."""
    fake = fakeredis.FakeRedis(decode_responses=True)

    import app as app_module

    monkeypatch.setattr(app_module, "redis_client", fake)

    # Reset counter for each test
    fake.delete("counter")

    yield fake


@pytest.fixture
def client(mock_redis):
    """Create a Flask test client."""
    import app as app_module

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as client:
        yield client


class TestGetCounter:
    """Tests for GET / endpoint."""

    def test_get_returns_zero_initially(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"Our counter is: 0" in response.data

    def test_get_returns_string(self, client):
        response = client.get("/")
        assert b"Our counter is:" in response.data


class TestPostCounter:
    """Tests for POST / endpoint."""

    def test_post_increments_counter(self, client):
        response = client.post("/")
        assert response.status_code == 200
        assert b"Hmm, Plus 1 please" in response.data

    def test_multiple_posts_increment(self, client):
        for i in range(5):
            client.post("/")
        response = client.get("/")
        assert b"Our counter is: 5" in response.data

    def test_get_reflects_posts(self, client):
        client.post("/")
        client.post("/")
        response = client.get("/")
        assert b"Our counter is: 2" in response.data


class TestHealthEndpoints:
    """Tests for health and readiness probes."""

    def test_healthz(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200

    def test_readyz(self, client):
        response = client.get("/readyz")
        assert response.status_code == 200


class TestMetrics:
    """Tests for Prometheus metrics endpoint."""

    def test_metrics_endpoint(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"http_requests_total" in response.data


class TestPersistence:
    """Tests for Redis persistence."""

    def test_counter_stored_in_redis(self, client, mock_redis):
        client.post("/")
        client.post("/")
        value = mock_redis.get("counter")
        assert int(value) == 2
