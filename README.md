# Counter Service

A lightweight Python-based HTTP counter service that counts POST requests and returns the current count on GET requests. Built for deployment on Kubernetes (EKS) with a fully automated CI/CD pipeline.

## Table of Contents

- [Overview](#overview)
- [Application](#application)
- [Docker](#docker)
- [Infrastructure](#infrastructure)
- [CI/CD](#cicd)
- [High Availability](#high-availability)
- [Production Considerations](#production-considerations)
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

The service persists the counter to a local JSON file. In Kubernetes, this file is stored on a PersistentVolumeClaim (PVC) backed by an encrypted EBS volume (gp3).

**Why file-based persistence?** It's the simplest approach — no additional infrastructure to provision or maintain. For a single-replica counter service, it works correctly: the counter survives pod restarts, crashes, and rescheduling because the EBS volume is independent of the pod lifecycle.

**Limitation: single replica only.** With file-based persistence, the counter is accurate with one replica and one gunicorn worker. Multiple replicas would each have their own PVC and their own counter, producing inconsistent results. This is a fundamental limitation of local file storage — not a bug, but an architectural trade-off.

**Alternative approaches considered:**

- **Redis** — would allow multiple replicas to share state, enabling true high availability with consistent counting across all pods. Adds operational complexity (another service to deploy, monitor, and secure) and a network dependency on every request. This is the recommended upgrade path if HA is required.
- **DynamoDB / RDS** — most durable option, survives even if the entire cluster goes down. Overkill for a counter, and adds latency, cost, and infrastructure to manage.
- **File on EFS (ReadWriteMany)** — would allow multiple replicas to mount the same filesystem. However, concurrent writes from multiple pods to the same file would require file locking to avoid corruption. EFS also has higher latency than EBS and adds cost.

The file-based approach was chosen for simplicity and correctness. The infrastructure and Kubernetes manifests (HPA, PDB, pod anti-affinity) are already in place to support multi-replica scaling — only the persistence layer would need to change to a shared store like Redis.

### High availability

The current deployment runs a single replica with the following HA-supporting infrastructure already in place:

- **HorizontalPodAutoscaler (HPA)** — configured to scale from 1 to 5 pods based on CPU utilization (70% threshold). With the current file-based persistence, scaled pods would each have independent counters. Switching to a shared store (Redis) would make this fully functional.
- **PodDisruptionBudget (PDB)** — ensures at least 1 pod remains available during voluntary disruptions like node drains and cluster upgrades.
- **Pod anti-affinity** — configured to prefer scheduling replicas on different nodes, so if the persistence layer is upgraded to support multiple replicas, they will be spread across nodes and AZs automatically.
- **Multi-AZ infrastructure** — worker nodes are spread across 2 Availability Zones at the Terraform level.

## Docker

### Image design

The service is packaged using a **multi-stage Docker build** to produce a minimal, secure image:

- **Stage 1 (builder)** — installs Python dependencies into an isolated prefix. Build tools and pip caches stay in this stage and are discarded.
- **Stage 2 (final)** — starts from a clean `python:3.12-slim` base, copies only the installed packages and application code. This keeps the final image around ~170MB instead of ~900MB.

Security measures applied in the image:

- Runs as a non-root user (`appuser`) — limits damage if the application is compromised.
- Uses `gunicorn` as the production WSGI server instead of Flask's development server, which is not designed for real traffic.
- Minimal image contents — no build tools, no caches, no test files.

### Build and run

```bash
# Build
docker build -t counter-service:test .

# Run
docker run -d --name counter-test -p 8080:8080 counter-service:test

# Verify
curl http://localhost:8080/
docker exec counter-test whoami   # should print: appuser

# Clean up
docker stop counter-test && docker rm counter-test
```

## Infrastructure

The entire AWS infrastructure is managed with Terraform, located in the `terraform/` directory.

### What gets provisioned

- **VPC** with 2 public subnets across 2 Availability Zones, internet gateway, and route tables.
- **EKS cluster** (Kubernetes 1.35) with `STANDARD` update policy, as required by the provided AWS account.
- **Managed node group** — 2 `t3.medium` nodes spread across both AZs for high availability.
- **ECR repository** — private Docker registry with image scanning enabled and a lifecycle policy that keeps only the last 10 images.
- **EBS encryption by default** — all new EBS volumes (node disks and PersistentVolumes) are automatically encrypted.

### Provisioning the cluster

```bash
# Prerequisites: AWS CLI and Terraform installed, AWS credentials configured
aws configure   # enter credentials, region: eu-west-2

cd terraform
terraform init    # download provider plugins
terraform plan    # review what will be created
terraform apply   # create the infrastructure (~15 min for EKS)

# Configure kubectl to talk to the new cluster
aws eks update-kubeconfig --name counter-service-cluster --region eu-west-2
kubectl get nodes   # verify: should show 2 nodes in Ready state
```

### Credentials and secrets

- AWS credentials are configured via `aws configure` or environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
- Credentials are never stored in code or committed to git. The `.gitignore` excludes `*.tfvars` and `*.tfstate` files.
- For CI/CD, AWS credentials are stored as GitHub Actions secrets (see [CI/CD](#cicd) section).

### Tear down

```bash
cd terraform
terraform destroy   # removes all AWS resources
```

## CI/CD

The project uses a GitHub Actions pipeline defined in `.github/workflows/ci-cd.yaml`. The pipeline is triggered on every push to `main` and on pull requests.

### Pipeline flow

**On pull requests:** CI only — runs tests to validate the change before merging.

**On push to main:** Full CI/CD:

1. **Test** — installs dependencies and runs the pytest suite.
2. **Build** — builds the Docker image for linux/amd64.
3. **Push** — pushes the image to ECR with two tags: the git commit SHA (for traceability) and `latest`.
4. **Deploy** — runs `helm upgrade --install` to deploy to the `prod` namespace on EKS.
5. **Verify** — waits for the rollout to complete and prints pod/service status.

Each deployment uses the git commit SHA as the image tag, so every deploy is traceable back to a specific commit. Rolling back is as simple as reverting the commit — the pipeline will redeploy the previous image.

### Setting up the pipeline

1. In your GitHub repository, go to **Settings → Secrets and variables → Actions**.
2. Add two repository secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
3. Push to `main` — the pipeline runs automatically.

### Rollback strategy

The Helm release keeps history of previous deployments. To rollback manually:

```bash
helm rollback counter-service 1    # roll back to revision 1
```

To rollback via CI/CD, revert the commit in git and push — the pipeline will redeploy the previous version.

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

## Production considerations

If this service were to run in a real production environment, the following improvements would be recommended:

- **Private subnets with NAT Gateway** — worker nodes are currently in public subnets for simplicity. In production, nodes should be in private subnets with a NAT Gateway for outbound internet access, reducing the attack surface.
- **Remote Terraform state** — state is currently stored locally. In a team environment, state should be stored in an S3 bucket with DynamoDB locking to enable collaboration and prevent conflicts.
- **Redis for persistence** — replacing file-based persistence with Redis would enable multiple replicas with shared state, achieving true high availability with consistent counting.
- **Sealed Secrets or External Secrets** — AWS credentials in GitHub Actions secrets work, but for production, a solution like AWS Secrets Manager with External Secrets Operator or Sealed Secrets provides better audit trails and rotation.
- **Canary deployments** — the current rolling update strategy could be enhanced with canary or blue-green deployments using tools like Argo Rollouts, allowing gradual traffic shifts and automated rollback on errors.
- **Grafana dashboard** — the Prometheus metrics endpoint is exposed and ready for scraping. Adding a Prometheus server and Grafana dashboard would provide visibility into request rates, counter values, and error rates.
