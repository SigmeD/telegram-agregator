# Infra — Telegram Lead Aggregator

Infrastructure, Docker, and deploy tooling for the monorepo. All commands
assume you run them from repo root (`D:\Project\Telegram Agregator\`) unless
noted.

## Layout

```
infra/
  docker/
    backend.Dockerfile         # multi-stage, one image for listener/worker/api/bot
    entrypoint.sh              # mode dispatcher
    frontend.Dockerfile        # optional self-host Next.js (Vercel is primary)
    .dockerignore              # applied by buildx from repo root
  compose/
    docker-compose.yml         # base stack (pg, redis, 4 services, migrate)
    docker-compose.dev.yml     # dev VPS override
    docker-compose.prod.yml    # prod VPS override (+ nginx)
    docker-compose.override.yml.example   # copy for local builds
  nginx/
    api.conf                   # TLS termination + reverse proxy to :8000
  scripts/
    deploy.sh                  # idempotent deploy with health-check + rollback
    rotate-session.sh          # Telethon session rotation (stub, see TODO)
    backup-db.sh               # pg_dump → gzip → S3 (stub, see TODO)
```

## One-image, four modes

The backend image has a single ENTRYPOINT (`entrypoint.sh`) that dispatches to:

| CMD        | Process                                |
| ---------- | -------------------------------------- |
| `listener` | `python -m listener`                   |
| `worker`   | `celery -A worker.celery_app worker`   |
| `beat`     | `celery -A worker.celery_app beat`     |
| `api`      | `uvicorn api.main:app`                 |
| `bot`      | `python -m bot`                        |
| `migrate`  | `alembic -c migrations/alembic.ini upgrade head` |
| `shell`    | `bash` (diagnostics)                   |

## Environments

| Env       | Trigger                                   | Target                    | Protection       |
| --------- | ----------------------------------------- | ------------------------- | ---------------- |
| `dev`     | `push` to `develop` + `backend/**` path   | Hetzner/Timeweb DEV VPS   | None (auto)      |
| `prod`    | `workflow_dispatch` only                  | Prod VPS                  | GitHub env = `production`, requires reviewers |
| frontend  | Git push                                   | Vercel                    | Vercel GitHub integration; self-host image is fallback only |

## Deploy flow (both envs, same script)

1. `docker compose pull` new tag.
2. `docker compose run --rm migrate` — Alembic upgrades are gated by a
   `pg_advisory_lock` inside `migrations/env.py` so parallel deploys can't
   collide.
3. `docker compose up -d` for all services (listener, worker, api, bot, +nginx
   in prod).
4. `curl /health` up to `HEALTH_ATTEMPTS × HEALTH_SLEEP` seconds.
5. On failure — restart services on the previous tag stored in
   `/var/lib/tlg-aggregator/last-good-tag`.
6. On success — record new tag as last-good.

Manual invocation on a VPS:

```bash
export POSTGRES_PASSWORD=...
infra/scripts/deploy.sh dev sha-abc1234
```

## GitHub Secrets

These MUST be set in the repository settings (Settings → Secrets and variables
→ Actions) or in the `production` environment. Never commit actual values.

### Infra / deploy

| Name              | Used by                 | Notes                                    |
| ----------------- | ----------------------- | ---------------------------------------- |
| `DEV_VPS_HOST`    | `cd-backend-dev.yml`    | `hostname` or IP of the dev VPS          |
| `DEV_VPS_USER`    | `cd-backend-dev.yml`    | ssh user, e.g. `deploy`                  |
| `DEV_SSH_KEY`     | `cd-backend-dev.yml`    | private key (PEM)                        |
| `DEV_SSH_PORT`    | `cd-backend-dev.yml`    | optional, default `22`                   |
| `PROD_VPS_HOST`   | `cd-backend-prod.yml`   | —                                        |
| `PROD_VPS_USER`   | `cd-backend-prod.yml`   | —                                        |
| `PROD_SSH_KEY`    | `cd-backend-prod.yml`   | —                                        |
| `PROD_SSH_PORT`   | `cd-backend-prod.yml`   | optional                                 |
| `GHCR_TOKEN`      | all image builds        | may be replaced by the default `GITHUB_TOKEN` with `packages: write` |

### Runtime / services (injected into `infra/env/backend.env` on the VPS)

| Name                 | Purpose                                    |
| -------------------- | ------------------------------------------ |
| `POSTGRES_PASSWORD`  | compose / migrate / deploy.sh              |
| `ANTHROPIC_API_KEY`  | primary LLM                                |
| `OPENAI_API_KEY`     | fallback LLM                               |
| `TELEGRAM_API_ID`    | Telethon auth                              |
| `TELEGRAM_API_HASH`  | Telethon auth                              |
| `NOTIFY_BOT_TOKEN`   | Aiogram notification bot                   |
| `JWT_SECRET`         | FastAPI auth                               |
| `TELETHON_SESSION_KEY` | Symmetric key used to encrypt the session file at rest and during rotation |
| `SENTRY_DSN`         | error reporting (all services)             |

## VPS preparation (one-off)

```bash
# 1. Docker + compose plugin
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker deploy

# 2. Clone repo (shallow is fine)
sudo mkdir -p /opt/tlg && sudo chown deploy:deploy /opt/tlg
git clone --depth 1 https://github.com/erohin-m/tlg-aggregator /opt/tlg

# 3. Provide env file (NOT committed)
sudo mkdir -p /opt/tlg/infra/env
sudo vi /opt/tlg/infra/env/backend.env   # fill with secrets listed above

# 4. First deploy
cd /opt/tlg && infra/scripts/deploy.sh dev develop
```

## Known tuning spots

Three places are intentionally stubbed and should be revisited after the first
live install — see the post-install notes in the repo.

1. **`rotate-session.sh` step 3** — importing a new Telethon session blob is
   a stub. Hook it up to whichever secret store you pick (HashiCorp Vault,
   1Password Connect, AWS SM).
2. **`backup-db.sh` endpoint** — upload assumes generic `aws s3 cp`. Choose
   Timeweb S3 / Backblaze B2 / plain AWS, set `S3_ENDPOINT`, and test restore.
3. **Resource limits in `docker-compose.prod.yml`** — guesses, not measured.
   After the first week of data, tune CPU/memory for postgres, worker
   concurrency, and API workers.
