FROM python:3.12-slim

WORKDIR /app

# Install Python dependencies (pinned in requirements.txt for fast, stable builds)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/

# Create required directories
RUN mkdir -p uploads data/jobs

# Expose port
EXPOSE 8000

# Health check (uses stdlib python — no extra apt packages needed)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz').status==200 else 1)" || exit 1

# Run with 1 worker (SQLite is not multi-process safe)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
