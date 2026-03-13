"""Tests for the counter service.

These tests verify the core functionality:
- GET returns the counter value
- POST increments the counter
- Health and readiness endpoints work
- Counter persists to file
"""

import json
import os
import tempfile

import pytest

# We need to set the COUNTER_FILE env var BEFORE importing app,
# because app.py reads it at import time when calling load_counter().
# This is a common pattern in testing: override config before import.

@pytest.fixture(autouse=True)
def setup_test_env(tmp_path):
    """Set up a temporary counter file for each test."""
    test_file = str(tmp_path / "counter.json")
    os.environ["COUNTER_FILE"] = test_file

    # We need to reimport/reset the app for each test because
    # the counter is loaded at module level.
    import app as app_module
    app_module.COUNTER_FILE = test_file
    app_module.counter = 0
    app_module.COUNTER_VALUE.set(0)

    yield app_module

    # Cleanup
    if os.path.exists(test_file):
        os.remove(test_file)


@pytest.fixture
def client(setup_test_env):
    """Create a Flask test client."""
    setup_test_env.app.config["TESTING"] = True
    with setup_test_env.app.test_client() as client:
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
        data = json.loads(response.data)
        assert data["status"] == "healthy"

    def test_readyz(self, client):
        response = client.get("/readyz")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "ready"


class TestMetrics:
    """Tests for Prometheus metrics endpoint."""

    def test_metrics_endpoint(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200
        assert b"http_requests_total" in response.data


class TestPersistence:
    """Tests for counter file persistence."""

    def test_counter_saved_to_file(self, client, setup_test_env):
        client.post("/")
        client.post("/")
        # Read the file directly
        with open(setup_test_env.COUNTER_FILE, "r") as f:
            data = json.load(f)
        assert data["counter"] == 2
