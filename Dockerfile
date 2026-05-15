# ── Kerf — single-image build (frontend + backend) ──────────────────────────
#
# Two-stage build: stage 1 compiles the Vite SPA → /app/dist; stage 2 is the
# Python runtime that pip-installs the chosen persona and copies the dist/
# folder for FastAPI StaticFiles to serve at `/`.
#
# Persona extras (install what you need for each pod type):
#   api-only      stateless API gateway + chat, no heavy compute
#   mech          full mechanical CAD stack
#   electronics   EDA / PCB / SPICE stack
#   bim           building information modelling stack
#   full          everything (monolith / dev)
#   compute-only  heavy compute workers only (no auth/API, behind internal LB)
#
# Build:
#   docker build --build-arg KERF_PERSONA=full -t kerf .
#
# ─────────────────────────────────────────────────────────────────────────────

# Stage 1: build the Vite SPA.
FROM node:22-alpine AS frontend
WORKDIR /app
COPY package.json package-lock.json* ./
# npm install (not ci): sharp/libvips pull platform-specific optional deps
# (@emnapi/*) that a darwin-generated lockfile can't fully pin for the
# linux/amd64 build image; install heals them while still honouring the lock.
RUN npm install --no-audit --no-fund
COPY vite.config.js index.html ./
COPY src/ ./src/
COPY public/ ./public/
COPY postcss.config.* tailwind.config.* eslint.config.* ./
RUN npm run build

# Stage 2: Python runtime.
FROM python:3.11-slim
ARG KERF_PERSONA=full

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy monorepo pyproject + all plugin packages.
COPY pyproject.toml ./
COPY packages/ ./packages/

# Install the selected persona (deps resolve from pyproject extras).
RUN pip install --no-cache-dir -e ".[$KERF_PERSONA]"

# Embed the compiled frontend.
COPY --from=frontend /app/dist /app/dist

ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV KERF_FRONTEND_DIST=/app/dist

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

CMD ["kerf-server", "--host", "0.0.0.0", "--port", "8080"]
