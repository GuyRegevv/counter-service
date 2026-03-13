# Counter Service

A lightweight Python-based HTTP counter service that counts POST requests and returns the current count on GET requests. Built for deployment on Kubernetes (EKS) with a fully automated CI/CD pipeline.

## Table of Contents

- [Overview](#overview)
- [Application](#application)
- [Quick Start](#quick-start)

---

## Overview

This project is a fork of [shainberg/counter-service](https://github.com/shainberg/counter-service), improved with production-readiness in mind: persistence, observability, health checks, security, and configuration management.

## Application

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Returns the current counter value |
| `/` | POST | Increments the counter by 1 |
| `/healthz` | GET | Liveness probe — is the process alive? |
| `/readyz` | GET | Readiness probe — is the app ready to serve traffic? |
| `/metrics` | GET | Prometheus metrics in standard exposition format |

### Improvements over the original

The original service stored the counter in memory and ran with `debug=True` on port 80. The improved version adds:

- **File-based persistence** — the counter is saved to `/data/counter.json` on every POST. When backed by a Kubernetes PersistentVolumeClaim, this survives pod restarts and rescheduling.
- **Configuration via environment variables** — `PORT`, `COUNTER_FILE`, `LOG_LEVEL`, and `APP_VERSION` are all configurable without code changes. This is the standard pattern in containerized environments, where Kubernetes ConfigMaps and Deployment manifests set env vars per environment.
- **Port 8080 instead of 80** — port 80 requires root privileges on Linux. Running containers as root is a security anti-pattern. Kubernetes maps external port 80 to internal port 8080 via the Service resource, so end users are unaffected.
- **Health and readiness endpoints** — Kubernetes uses `/healthz` (liveness probe) to decide whether to restart a pod, and `/readyz` (readiness probe) to decide whether to send traffic to it. The readiness probe verifies the data directory is writable.
- **Prometheus metrics** — exposes `http_requests_total` (a Counter tracking requests by method/endpoint/status) and `counter_current_value` (a Gauge showing the current count). These can be scraped by Prometheus and visualized in Grafana.
- **Structured JSON logging** — logs are emitted as JSON to stdout, which log aggregation tools (CloudWatch, Loki, ELK) can parse and index automatically. Plain text logs require custom parsing rules.
- **Thread-safe counter** — a threading lock protects the counter from race conditions when running under a multi-worker server like gunicorn.
- **Debug mode disabled** — `debug=True` exposes stack traces and enables a remote debugger, which is a security risk in production.
- **Pinned dependency versions** — `requirements.txt` pins exact versions to ensure reproducible builds. Without pinning, a new release of a dependency could break the build unexpectedly.
- **Tests** — 9 tests covering GET, POST, health endpoints, metrics, and persistence. These run in CI to catch regressions before deployment.

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `COUNTER_FILE` | `/data/counter.json` | Path to the persistence file |
| `PORT` | `8080` | Port the service listens on |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `APP_VERSION` | `0.1.0` | Version string returned in responses |

### Persistence — approach and trade-offs

The service persists the counter to a local JSON file. In Kubernetes, this file is stored on a PersistentVolumeClaim (PVC) backed by an encrypted EBS volume.

**Why file-based persistence?** It's the simplest approach — no additional infrastructure to provision or maintain. For a single-replica counter service, it works well.

**Alternative approaches considered:**

- **Redis** — would allow multiple replicas to share state, enabling true high availability. Adds operational complexity (another service to deploy, monitor, and secure) and a network dependency on every request.
- **DynamoDB / RDS** — most durable option, survives even if the entire cluster goes down. Overkill for a counter, and adds latency, cost, and infrastructure to manage.
- **File on EFS (ReadWriteMany)** — would allow multiple replicas to share a file. EFS has higher latency than EBS and adds cost, but avoids running a separate data store.

The file-based approach was chosen for simplicity. For a production service with HA requirements, Redis or DynamoDB would be more appropriate.

## Quick Start

### Run locally

```bash
pip install -r requirements.txt
COUNTER_FILE=/tmp/counter.json python app.py
```

### Test

```bash
# Run the test suite
pytest test_app.py -v

# Manual testing
curl http://localhost:8080/          # GET  — view counter
curl -X POST http://localhost:8080/  # POST — increment counter
curl http://localhost:8080/healthz   # Health check
curl http://localhost:8080/readyz    # Readiness check
curl http://localhost:8080/metrics   # Prometheus metrics
```
