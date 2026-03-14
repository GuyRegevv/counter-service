"""Counter Service - A lightweight HTTP counter API."""

import json
import logging
import os
import sys
import threading

from flask import Flask, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

# --- Configuration ---
COUNTER_FILE = os.environ.get("COUNTER_FILE", "/data/counter.json")
PORT = int(os.environ.get("PORT", "8080"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
APP_VERSION = os.environ.get("APP_VERSION", "0.1.0")


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


# --- Counter persistence ---
# Lock prevents race conditions with concurrent workers
counter_lock = threading.Lock()


def load_counter() -> int:
    """Load the counter value from the persistence file."""
    try:
        with open(COUNTER_FILE, "r") as f:
            data = json.load(f)
            value = data.get("counter", 0)
            logger.info(f"Loaded counter value: {value}")
            return value
    except FileNotFoundError:
        logger.info("No existing counter file found, starting from 0")
        return 0
    except (json.JSONDecodeError, KeyError) as e:
        logger.warning(f"Corrupted counter file, resetting to 0: {e}")
        return 0


def save_counter(value: int) -> None:
    """Save the counter value to the persistence file."""
    try:
        os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)
        with open(COUNTER_FILE, "w") as f:
            json.dump({"counter": value}, f)
    except OSError as e:
        logger.error(f"Failed to save counter: {e}")


# --- Flask application ---
app = Flask(__name__)
counter = load_counter()
COUNTER_VALUE.set(counter)


@app.route("/", methods=["GET"])
def get_counter():
    """Return the current counter value."""
    REQUEST_COUNT.labels(method="GET", endpoint="/", status=200).inc()
    return f"Our counter is: {counter} "


@app.route("/", methods=["POST"])
def increment_counter():
    """Increment the counter by 1 and persist it."""
    global counter
    with counter_lock:
        counter += 1
        save_counter(counter)
        COUNTER_VALUE.set(counter)
    REQUEST_COUNT.labels(method="POST", endpoint="/", status=200).inc()
    logger.info(f"Counter incremented to {counter}")
    return "Hmm, Plus 1 please..."


@app.route("/healthz", methods=["GET"])
def health():
    """Liveness probe endpoint."""
    return jsonify({"status": "healthy"}), 200


@app.route("/readyz", methods=["GET"])
def ready():
    """Readiness probe - verifies the data directory is writable."""
    try:
        os.makedirs(os.path.dirname(COUNTER_FILE), exist_ok=True)
        test_path = os.path.join(os.path.dirname(COUNTER_FILE), ".ready_check")
        with open(test_path, "w") as f:
            f.write("ok")
        os.remove(test_path)
        return jsonify({"status": "ready"}), 200
    except OSError:
        logger.warning("Readiness check failed - cannot write to data directory")
        return jsonify({"status": "not ready", "reason": "storage unavailable"}), 503


@app.route("/metrics", methods=["GET"])
def metrics():
    """Expose Prometheus metrics."""
    return generate_latest(), 200, {"Content-Type": CONTENT_TYPE_LATEST}


if __name__ == "__main__":
    logger.info(f"Starting counter service v{APP_VERSION} on port {PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
