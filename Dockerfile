FROM python:3.12-slim

WORKDIR /app

# Install system deps (curl needed for health check)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/

# Create required directories
RUN mkdir -p uploads data/jobs

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD curl -f http://localhost:8000/healthz || exit 1

# Run with 1 worker (SQLite is not multi-process safe)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
