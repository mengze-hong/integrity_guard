# Configuration

All configuration lives in `app/config.py`. This document lists every setting, its default, and how it is sourced. It reflects the code at app version `5.3.83`.

## Sourcing Order

Secrets are resolved by `app/secrets_manager.py` in this order:

1. **Environment variable** (highest priority).
2. **Encrypted store** at `data/secrets.enc` (master key in the OS credential vault via `keyring`).

No secret is hardcoded in `config.py` (the file is tracked by git). Some secrets are auto-generated and persisted to the encrypted store on first use (`get_or_create_secret`).

A local `.env` file is loaded for convenience if present, but the canonical store is the encrypted one. Run `python -m app.secrets_setup` to migrate `.env` secrets into the encrypted store and remove the plaintext file.

Never commit `.env`, `data/secrets.enc`, `data/.jwt_secret`, or `data/.admin_key`.

## Secrets

| Name | Env var | Default | Source | Purpose |
|---|---|---|---|---|
| LLM API key | `LLM_API_KEY` | `""` | env → encrypted store | Internal LiteLLM API key. Sensitive. |
| LLM base URL | `LLM_BASE_URL` | `""` | env → encrypted store | Internal LLM endpoint. **Treated as sensitive** — never logged or exposed in health responses. |
| LLM model | `LLM_MODEL` | `gpt-5.2` | env → encrypted store | Default model name. |
| JWT secret | `JWT_SECRET` | auto-generated (32 bytes) | env → encrypted store (created if absent) | Signs auth JWTs. Persisted so restarts do not log users out. |
| Admin key | `ADMIN_KEY` | auto-generated (16 bytes) | env → encrypted store (created if absent) | Authorizes the admin credit endpoint. |
| Alipay app id | `ALIPAY_APP_ID` | `""` | env → encrypted store | Alipay integration (sandbox/MVP). |
| Alipay private key | `ALIPAY_PRIVATE_KEY` | `""` | env → encrypted store | Alipay signing key. Not used for real production signing yet. |
| Alipay public key | `ALIPAY_PUBLIC_KEY` | `""` | env → encrypted store | Alipay verification key. |

Set a secret interactively:

```bash
python -m app.secrets_setup --set LLM_API_KEY
python -m app.secrets_setup --set LLM_BASE_URL
python -m app.secrets_setup --set LLM_MODEL
```

Confirm which secret names are stored (values are never printed):

```bash
python -m app.secrets_setup --show
```

## LLM Usage Caps

Module-level constants in `config.py`, read from environment variables at import time. These limit AI cost/abuse.

| Constant | Env var | Default | Meaning |
|---|---|---|---|
| `LLM_RATE_PER_IP` | `LLM_RATE_PER_IP` | `30` | Max LLM requests per IP per window. |
| `LLM_RATE_WINDOW` | `LLM_RATE_WINDOW` | `3600` | Rate-limit window in seconds. |
| `LLM_GLOBAL_HOURLY_CAP` | `LLM_GLOBAL_HOURLY_CAP` | `500` | Global LLM requests per hour across all users. |

Rate limiting is in-memory and resets on restart; it is not multi-instance safe (see `HANDOVER.md`).

## Server

| Setting | Env var | Default | Notes |
|---|---|---|---|
| `host` | — | `0.0.0.0` | Bind address. For local-only demos, run uvicorn with `--host 127.0.0.1`. |
| `port` | — | `8000` | Bind port. |
| `app_env` | `APP_ENV` | `local` | Lowercased. `prod`/`production` enables production-risk checks in `/readyz` (e.g. payment sandbox is flagged degraded). |

## Paths

| Setting | Default | Purpose |
|---|---|---|
| `upload_dir` | `uploads` | Uploaded and extracted paper projects. Created at startup. Not committed. |
| `data_dir` | `data` | SQLite DB, encrypted secret store, job reports. Not committed. |

## Crossref

| Setting | Default | Purpose |
|---|---|---|
| `crossref_base_url` | `https://api.crossref.org` | Crossref API base. |
| `crossref_email` | `mengzehong@example.com` | Polite-pool contact email. Change for production use. |
| `crossref_timeout` | `10.0` | Request timeout (seconds). |
| `crossref_max_concurrent` | `5` | Max concurrent Crossref requests. |

## Gate Thresholds

| Setting | Default | Purpose |
|---|---|---|
| `reference_confidence_threshold` | `60.0` | Gate score below this fails the gate. |
| `max_missing_doi_ratio` | `0.0` | `0` means every entry must have a DOI. |

## Auth & Billing

| Setting | Default | Purpose |
|---|---|---|
| `jwt_expire_days` | `7` | JWT lifetime in days. |
| `credits_upload` | `1` | Credits per full check (upload). |
| `credits_recheck` | `0` | Recheck is free (already paid on upload). |
| `credits_ai_fix` | `0` | AI fix is free (value-add experience). |
| `credits_bib_clean` | `0` | Bib clean tool is free. |
| `credits_tidyup` | `0` | Tidyup tool is free. |

Pro/Team tiers get unlimited full checks and do not consume credits. Free tier starts with 3 checks and gets a monthly lazy refresh.

## Payment

| Setting | Env var | Default | Notes |
|---|---|---|---|
| `payment_sandbox` | `PAYMENT_SANDBOX` | `true` | Sandbox auto-credits on payment. **Must be disabled in production** — `/readyz` reports degraded if `app_env` is production and this is true. |

Real Alipay production signing/verification is not implemented. Sandbox mode is for MVP testing only.

## Configuration Tips

- For a local-only run, you typically only need `LLM_API_KEY`, `LLM_BASE_URL`, and optionally `LLM_MODEL`. JWT and admin keys auto-generate.
- AI features degrade gracefully when LLM config is missing: rule-based gates still run; AI endpoints return clear errors instead of crashing.
- For production, set `APP_ENV=production`, disable `PAYMENT_SANDBOX`, inject secrets via environment variables or the encrypted store, and protect `/metrics` and the admin endpoint behind a reverse proxy. See `DEPLOY_SAFE.md`.

## Related Documents

- [ARCHITECTURE.md](ARCHITECTURE.md) — system structure.
- [LOCAL_RUN.md](LOCAL_RUN.md) — local setup and secret initialization.
- [DEPLOY_SAFE.md](DEPLOY_SAFE.md) — production switches and secret injection.
