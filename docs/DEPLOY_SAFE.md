# Safe Production Deployment

Use this guide before exposing ScholarLint to real users or any public network.

## Recommended Deployment Shape

- Run the application in Docker, preferably from the checked-in `Dockerfile` and `docker-compose.yml` rather than a local development process.
- Put a production reverse proxy in front of the app for TLS termination, request size limits, access logs, compression, and security headers.
- Serve all public traffic over HTTPS. Do not expose the app directly over plain HTTP on the public internet.
- Use localhost-only binding for the app container or process, and expose only the reverse proxy to the network.

## Production Switches

- Set `APP_ENV=production` for production deployments.
- Confirm `PAYMENT_SANDBOX=false` before accepting real payments or selling credits.
- Check `/readyz` after setting production variables. A production deployment with sandbox payment enabled should be treated as not ready for launch.

## Secrets

- Inject secrets from environment variables or an encrypted secret store.
- Do not commit `.env`, `.env.*`, `data/secrets.enc`, private keys, payment credentials, JWT secrets, admin credentials, or webhook secrets.
- Keep secrets out of command examples, screenshots, logs, issue comments, and release notes.
- Rotate any secret that may have appeared in a tracked file or public transcript.

## Upload And ZIP Safety

- Keep upload request size limits enabled at the reverse proxy and app layers.
- Preserve ZIP safety checks for path traversal, symlinks, suspicious compression ratios, excessive member counts, dangerous extensions, and cleanup after failed extraction.
- Keep uploaded archives and extracted work directories on a dedicated data volume, not inside the application source tree.
- Review retention and cleanup settings before launch so user uploads do not remain indefinitely.

## Logs And Probes

- Collect structured application logs from the container or process supervisor.
- Keep access logs at the reverse proxy for request tracing, abuse investigation, and incident response.
- Do not log raw secrets, internal endpoints, payment payload secrets, user tokens, or uploaded paper content.
- Use `/healthz` as the liveness probe.
- Use `/readyz` as the readiness probe before routing production traffic.
- Use `/metrics` for lightweight uptime, request count, latency, and server error-rate checks. Treat it as operational metadata and expose it only behind the same production access controls as the rest of the service.

## Backups

- Back up the data directory that stores the SQLite database, encrypted job reports, payment/order state, and encrypted secrets where applicable. Use `python scripts/backup_data.py` for a local archive and see `docs/BACKUP.md` for restore steps.
- Test restore on a separate environment before relying on backups.
- Keep backup storage access restricted and encrypted.
- Do not back up temporary upload extraction directories unless there is a clear retention requirement.

## Public Exposure Checklist

Before any formal public exposure, confirm all of the following:

- Authentication is enabled for write actions and private job access.
- Rate limiting is enabled for uploads, login/register, admin actions, and LLM-backed features.
- HTTPS is enforced at the public edge.
- Reverse proxy and application logs are collected and reviewed.
- Upload size, ZIP safety, retention, and cleanup policies are active.
- Secrets are injected from environment variables or encrypted storage, with no `.env` files committed.
- `APP_ENV=production` is set.
- `PAYMENT_SANDBOX=false` is set if real payments are enabled.
- `/healthz` and `/readyz` both return expected production status.
- Any temporary public tunnel provider or similar forwarding service has been removed unless explicitly approved for a short, monitored demo with the same authentication, rate limiting, HTTPS, logging, and cleanup checks.
