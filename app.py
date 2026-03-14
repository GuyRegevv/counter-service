"""Counter Service - A lightweight HTTP counter API."""

import json
import logging
import os
import sys

import redis
from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

# --- Configuration ---
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
PORT = int(os.environ.get("PORT", "8080"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")
COUNTER_KEY = "counter"


# --- Structured JSON logging ---
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=LOG_LEVEL, handlers=[handler])
logger = logging.getLogger(__name__)


# --- Prometheus metrics ---
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "status"],
)
COUNTER_VALUE = Gauge(
    "counter_current_value",
    "The current value of the POST counter",
)


# --- Redis connection ---
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


# --- Flask application ---
app = Flask(__name__)


@app.route("/", methods=["GET"])
def get_counter():
    """Return the current counter value."""
    REQUEST_COUNT.labels(method="GET", endpoint="/", status=200).inc()
    value = int(redis_client.get(COUNTER_KEY) or 0)
    COUNTER_VALUE.set(value)
    return f"Our counter is: {value} "


@app.route("/", methods=["POST"])
def increment_counter():
    """Increment the counter by 1."""
    value = redis_client.incr(COUNTER_KEY)
    COUNTER_VALUE.set(value)
    REQUEST_COUNT.labels(method="POST", endpoint="/", status=200).inc()
    logger.info(f"Counter incremented to {value}")
    return "Hmm, Plus 1 please! "


@app.route("/healthz", methods=["GET"])
def health():
    """Liveness probe endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/readyz", methods=["GET"])
def ready():
    """Readiness probe - verifies Redis is reachable."""
    try:
        redis_client.ping()
        return jsonify({"status": "ready"}), 200
    except redis.ConnectionError:
        logger.warning("Readiness check failed - cannot connect to Redis")
        return jsonify({"status": "not ready", "reason": "redis unavailable"}), 503


@app.route("/metrics", methods=["GET"])
def metrics():
    """Expose Prometheus metrics."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    logger.info(f"Starting counter service v{APP_VERSION} on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
