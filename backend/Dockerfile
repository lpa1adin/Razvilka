# Один образ для api и всех воркеров: код общий, отличается только команда запуска (ADR-001).
FROM python:3.12-slim AS app

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /usr/local/bin/uv
# git нужен сборщику: источники забираются неглубокой копией репозитория
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"

WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY . .

# Код ученика (runner, этап 2) будет выполняться от этого пользователя без прав.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /var/cache/razvilka/sources && chown -R app /var/cache/razvilka
USER app

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]

# Образ runner: всё то же + Chromium для веб-заданий (около 1,5 ГБ, поэтому только здесь)
FROM app AS runner
USER root
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN uv sync --frozen --no-install-project --group runner \
    && playwright install --with-deps chromium \
    && chmod -R o+rx /ms-playwright
USER app
CMD ["python", "-m", "app.workers", "runner"]

