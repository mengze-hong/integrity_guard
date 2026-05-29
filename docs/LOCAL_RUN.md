# Local Run Guide

This guide covers a local-only ScholarLint run for development or demos. Keep demos bound to localhost unless a deployment plan explicitly approves a public exposure path.

## 1. Install Dependencies

Use Python 3.11 or newer.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
npm install
```

If editable install is not available in your environment, install the runtime requirements directly:

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest pytest-cov ruff pip-audit
npm install
```

## 2. Initialize Secrets

Secrets are loaded from environment variables first, then from the encrypted store at `data/secrets.enc`.

For first-time local setup or migration from legacy plaintext files, run:

```powershell
python -m app.secrets_setup
```

To set one secret interactively:

```powershell
python -m app.secrets_setup --set LLM_API_KEY
python -m app.secrets_setup --set LLM_BASE_URL
python -m app.secrets_setup --set LLM_MODEL
```

To confirm which secret names are stored without printing values:

```powershell
python -m app.secrets_setup --show
```

Never commit `.env`, `data/secrets.enc`, `data/.jwt_secret`, or `data/.admin_key`.

## 3. Start Locally

Run the FastAPI app from the repository root. For local-only demos, bind to loopback:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

If port `8000` is already in use, choose another local port:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001
```

Open `http://localhost:8000` or the port you selected.

## 4. Docker Compose

Docker Compose builds the app and mounts local state directories into the container:

```powershell
docker compose up --build
```

The compose file maps `127.0.0.1:8000:8000` and persists local state. Containerized app servers can still bind to `0.0.0.0` inside the container so Docker can publish the loopback-only mapped port:

- `./data` to `/app/data`
- `./uploads` to `/app/uploads`

Stop it with:

```powershell
docker compose down
```

## 5. Health Checks

Use these probes after the app starts:

```powershell
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/readyz
```

`/healthz` confirms the process is alive and returns the service version. `/readyz` checks database, encrypted secret support, LLM configuration, payment sandbox state, and storage directories with sanitized status fields only.

## 6. Local Data Directories

Local runtime state lives under:

- `data/integrity.db` — SQLite database.
- `data/secrets.enc` — encrypted local secret store.
- `uploads/` — uploaded and extracted paper projects.
- `data/jobs/` — generated job/report state when present.

These are local/generated artifacts and should not be committed.

## 7. Demo Boundary

Use localhost for development and demos. Do not expose the dev server through a temporary public tunnel provider or other public tunnel unless the release owner has approved the risk, secret posture, and cleanup plan.
