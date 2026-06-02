# Tencent Cloud Lighthouse Deployment

This guide deploys ScholarLint to a single Tencent Cloud Lighthouse
instance (轻量应用服务器) using the checked-in `Dockerfile` /
`docker-compose.yml`. It assumes you have read [`DEPLOY_SAFE.md`](DEPLOY_SAFE.md)
first — that one is the source of truth for security invariants; this
file only adds the Tencent-specific steps.

> **Hard rules (do not relax)**
> * **Never** push secrets through `git`. The repo's `.gitignore` already
>   blocks `.env` / `data/secrets.enc` / `data/.jwt_secret` /
>   `data/.admin_key`; do not work around them.
> * **Never** put real LLM keys, JWT secrets, admin keys, or Alipay
>   private keys in any tracked file (no commit messages, no shell
>   history committed via `Makefile`, no GitHub Actions secrets without
>   masking).
> * Cloudflare and any third-party public tunnel are forbidden — CI's
>   tunnel scan will reject the change. Use Tencent Cloud's own SSL +
>   Nginx reverse proxy instead.

---

## 1. Pick the instance

| Stage | Suggested spec | Notes |
|---|---|---|
| MVP / pilot | Lighthouse 通用型 2C2G + 50GB SSD + 4Mbps | About ¥30-60/month. Good for dozens of daily users. |
| Growth | Lighthouse 通用型 2C4G + 80GB SSD + 6-8Mbps | Comfortable for hundreds. Bumps RAM for LLM concurrency. |
| Scale-out | Migrate to CVM SA/S5 + CLB + Redis | Out of scope here; do this after `/metrics` shows sustained load. |

**Region**: Pick the same region as your dominant user base. For mainland
ICP-pending stage, use 香港 (Hong Kong) or 新加坡 — those Lighthouse
SKUs do not require ICP filing for the public domain.

**Image**: `Ubuntu 22.04 LTS`. Avoid the bundled "Docker" application
image — it ships an older Docker; install fresh from `get.docker.com`
for predictable behaviour.

## 2. Server bootstrap (one-time)

SSH into the instance with the key you set during purchase. Run as a
non-root sudo user when possible:

```bash
# Update + install Docker
sudo apt-get update && sudo apt-get install -y curl ca-certificates ufw
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker

# Firewall (Lighthouse also has its own firewall in console — keep both
# layers tight; enable only 22/80/443 to the public).
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable

# Optional but recommended: separate data disk (Lighthouse "数据盘")
# mounted at /srv/scholarlint so reinstalling the OS leaves data alone.
# Tencent console → 实例详情 → 挂载数据盘 → 在主机上 mkfs.ext4 + mount
# Then symlink (or just clone the repo into) /srv/scholarlint.
```

## 3. Clone the repo (no secrets yet)

```bash
sudo mkdir -p /srv/scholarlint && sudo chown "$USER:$USER" /srv/scholarlint
cd /srv/scholarlint
git clone https://github.com/mengze-hong/integrity_guard.git app
cd app
```

The repo is **safe to clone** — `.gitignore` has been audited to keep
secrets, uploads, and `data/secrets.enc` out of the public history.
Confirm by running:

```bash
git ls-files | grep -E '^\.env|secrets\.enc|\.jwt_secret|\.admin_key' || echo "clean"
```

You should see `clean`.

## 4. Inject secrets — server-side only

This is the part that must **never** travel through git, Slack,
WeChat, or AI chat logs. Two acceptable channels:

* **Tencent Cloud SSM Parameter Store**: stash each secret as a
  SecureString, then use `tccli ssm GetParameter` in a one-shot
  bootstrap script that pipes the value into a runtime-only env file.
* **Manual `.env` on the box**: paste once via SSH, set strict perms.

The simplest path:

```bash
# /srv/scholarlint/app/.env  (the file is already in .gitignore)
cat > .env << 'EOF'
APP_ENV=production
PAYMENT_SANDBOX=false

# LLM gateway — supplied via Tencent Cloud internal LiteLLM endpoint
LLM_API_KEY=__paste_here__
LLM_BASE_URL=__paste_here__
LLM_MODEL=gpt-5.2

# Auth + admin — leave empty to let the app generate and persist them
# under data/.jwt_secret and data/.admin_key. Generation is idempotent;
# do NOT regenerate after launch (would invalidate active sessions).
# JWT_SECRET=
# ADMIN_KEY=

# Alipay — only set when accepting real payments
# ALIPAY_APP_ID=
# ALIPAY_PRIVATE_KEY=
# ALIPAY_PUBLIC_KEY=

# Operational tuning (defaults are fine for MVP)
LLM_RATE_PER_IP=30
LLM_RATE_WINDOW=3600
LLM_GLOBAL_HOURLY_CAP=500
CROSSREF_EMAIL=ops@your-domain.com
EOF
chmod 600 .env
```

`docker-compose.yml` already reads `.env` automatically; no extra wiring
needed.

> **Why the JWT secret is generated on the box, not committed:** the
> app calls `get_or_create_secret("JWT_SECRET", 32)` which writes a
> 32-byte random key into `data/.jwt_secret` on first run. That file
> is in `.gitignore`. The same applies to `ADMIN_KEY`. Treat them like
> the SSH host key — back them up to Tencent Cloud COS encrypted, not
> to GitHub.

## 5. Bring it up

```bash
# Make sure compose binds only to localhost — the existing
# docker-compose.yml maps "127.0.0.1:8000:8000". DO NOT change that to
# "0.0.0.0:8000". Public traffic goes through Nginx.
docker compose up -d

# Verify health and readiness
curl -fsS http://127.0.0.1:8000/healthz   # {"status":"ok"}
curl -fsS http://127.0.0.1:8000/readyz    # production switches honoured
```

If `/readyz` complains about `payment_sandbox=true`, you forgot the
production switch — fix `.env` and `docker compose up -d` to apply.

## 6. Nginx + HTTPS (Tencent Cloud SSL, no Cloudflare)

Use the **Tencent Cloud SSL certificate service** (free DV cert,
1-year, auto-renewable). Issue from the console, then:

```bash
sudo apt-get install -y nginx
sudo mkdir -p /etc/nginx/certs
# Upload fullchain.pem and privkey.pem from the console download
sudo cp ~/scholarlint.cer /etc/nginx/certs/fullchain.pem
sudo cp ~/scholarlint.key /etc/nginx/certs/privkey.pem
sudo chmod 600 /etc/nginx/certs/privkey.pem
```

Drop in `/etc/nginx/sites-available/scholarlint`:

```nginx
# 1. Force HTTPS
server {
    listen 80;
    server_name your-domain.example;
    return 301 https://$host$request_uri;
}

# 2. The real vhost
server {
    listen 443 ssl http2;
    server_name your-domain.example;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Bound the LaTeX-project upload size; 30M is generous.
    client_max_body_size 30M;

    # ScholarLint already streams large jobs; turn off proxy buffering
    # so progress polling stays responsive.
    proxy_buffering off;
    proxy_request_buffering off;

    # Forward HTTPS context so the app's _secure_session_cookie() and
    # auth_routes._secure_cookie() flip the Secure flag automatically.
    proxy_set_header Host              $host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto https;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_read_timeout 120s;   # gates can take ~30s on big projects
    }

    # Lock /metrics to your office IP / VPN.
    location /metrics {
        # allow 1.2.3.4;
        # deny all;
        proxy_pass http://127.0.0.1:8000/metrics;
    }
}
```

```bash
sudo ln -sf /etc/nginx/sites-available/scholarlint /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

## 7. Backups

The data that matters: `data/integrity.db`, `data/jobs/*.enc`,
`data/.jwt_secret`, `data/.admin_key`, `data/secrets.enc`.

`scripts/backup_data.py` is the supported entry point. Drop a daily
crontab on the host, push the resulting tarball to **Tencent Cloud COS**
(via `coscmd`) — encrypted bucket, no public read.

```bash
# /etc/cron.d/scholarlint-backup
30 3 * * *  ubuntu  cd /srv/scholarlint/app && \
  python scripts/backup_data.py && \
  coscmd upload backups/$(date +\%F).tar.gz scholarlint-backup/
```

> Never push the backup directory or its tarballs through git.
> Never store secrets in COS object metadata or filenames.

## 8. ICP filing (mainland regions only)

* Hong Kong / Singapore Lighthouse → **no filing required**, you can
  serve `your-domain.example` immediately.
* Mainland regions (Beijing / Shanghai / Guangzhou / etc.) → **ICP
  filing 备案 is mandatory before pointing any domain there.** Use
  Tencent Cloud's wizard (实名 + 域名 + 主体材料), allow 7-20 working
  days. Until the filing is approved, traffic on port 80/443 from
  unfiled domains is silently dropped at the upstream BGP — there is
  no way to bypass this.

## 9. Operational checklist (run before launch)

```bash
# Production switches honoured
curl -s https://your-domain.example/readyz | grep '"ready":true'

# Static health probe answers
curl -fsS https://your-domain.example/healthz

# Secret scan + tunnel scan locally before the next push
node scripts/secret-scan.mjs
git grep -n -i -E 'cloudflared|trycloudflare|cloudflare' \
  -- . ':!CHANGELOG.md' ':!WORK_PLAN.md' || echo OK

# .env is not tracked
git ls-files | grep -E '^\.env(\.|$)' && echo "LEAK" || echo "ok"

# data/secrets.enc is not tracked
git ls-files | grep secrets.enc && echo "LEAK" || echo "ok"
```

If any of those fail, **do not deploy**.

## 10. Updating

```bash
cd /srv/scholarlint/app
git fetch origin main && git checkout main && git pull --ff-only
docker compose pull   # (if you push images to TCR; otherwise skip)
docker compose build
docker compose up -d
curl -fsS https://your-domain.example/readyz
```

Roll back is trivially `git checkout <previous-tag> && docker compose up -d`
because every release commit is independently revertable (see
`CHANGELOG.md` versioning policy).

---

## Out of scope here

* Multi-instance / load balancer (`CLB`): wait until `/metrics` shows
  sustained load > 1 RPS for 5 minutes.
* TKE / serverless: rewrite-required; the current SQLite + on-disk
  encrypted secrets do not match a stateless 12-factor model.
* Object Storage for uploads: the upload pipeline writes to local
  `uploads/` then extracts; moving that to COS needs application
  changes (separate workitem).

When you reach those, open a new doc — do not extend this one.
