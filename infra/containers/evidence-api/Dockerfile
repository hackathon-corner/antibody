# Evidence API + dashboard (owner: C). One container: FastAPI serves /api/* and the built dashboard at /.
# Build context is the repo root; .dockerignore allowlists only what this image needs (never .env).
# Base images come from the ECR mirror of Docker Hub official images (Docker Hub rate-limits CI pulls: 429).
# ClickHouse settings come from the host's environment at runtime (CLICKHOUSE_* in .env.example).

FROM public.ecr.aws/docker/library/node:22-bookworm-slim AS web
WORKDIR /web
COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY src/web/ ./
RUN npm run build

FROM public.ecr.aws/docker/library/python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ANTIBODY_WEB_DIST=/app/web
WORKDIR /app
COPY pyproject.toml ./
COPY src/ src/
RUN pip install --no-cache-dir . && rm -rf src build
COPY --from=web /web/dist /app/web
USER nobody
EXPOSE 8000
CMD ["uvicorn", "server.app:app", "--host", "0.0.0.0", "--port", "8000"]
