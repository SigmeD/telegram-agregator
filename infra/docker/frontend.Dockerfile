# syntax=docker/dockerfile:1.7
# =============================================================================
# Telegram Lead Aggregator — frontend (Next.js) self-host image.
#
# Primary deploy target is Vercel. This image exists as a fallback for
# on-prem / air-gapped self-hosting. Uses Next.js "standalone" output.
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: deps — install production + dev deps with pnpm.
# -----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS deps

ENV PNPM_HOME=/pnpm \
    PATH="/pnpm:$PATH" \
    CI=1

RUN corepack enable \
    && corepack prepare pnpm@9.12.0 --activate

WORKDIR /app

COPY frontend/package.json frontend/pnpm-lock.yaml* ./
RUN --mount=type=cache,id=pnpm,target=/pnpm/store \
    pnpm install --frozen-lockfile || pnpm install

# -----------------------------------------------------------------------------
# Stage 2: build — produce `.next/standalone` bundle.
# -----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS builder

ENV PNPM_HOME=/pnpm \
    PATH="/pnpm:$PATH" \
    NEXT_TELEMETRY_DISABLED=1

RUN corepack enable \
    && corepack prepare pnpm@9.12.0 --activate

WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY frontend/ ./

# Build-time public env vars must be passed as --build-arg (API URL etc).
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN pnpm build

# -----------------------------------------------------------------------------
# Stage 3: runtime — minimal distroless-ish image.
# -----------------------------------------------------------------------------
FROM node:20-bookworm-slim AS runtime

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME=0.0.0.0

RUN groupadd --system --gid 1001 nodejs \
    && useradd --system --uid 1001 --gid nodejs nextjs

WORKDIR /app

# Next.js standalone output keeps only what is actually needed at runtime.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:' + (process.env.PORT||3000)).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
