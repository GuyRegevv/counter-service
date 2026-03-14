# ---- Build stage ----
# Install dependencies in a temporary image that we throw away.
# This keeps build tools out of the final image.
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---- Final stage ----
FROM python:3.12-slim

# Create a non-root user to run the application
RUN groupadd --system appuser && \
    useradd --system --gid appuser --create-home appuser

WORKDIR /app

# Copy installed Python packages from the builder stage
COPY --from=builder /install /usr/local

# Copy application code
COPY app.py .

# Switch to non-root user
USER appuser

# Expose the application port (documentation — doesn't actually open the port)
EXPOSE 8080

ENV PORT=8080
ENV LOG_LEVEL=INFO

# Use gunicorn for production instead of Flask's dev server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--access-logfile", "-", "app:app"]
