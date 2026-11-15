# Field Shift API image (FastAPI).
# The heavy inputs in data/raw and data/processed are not baked into the image: the entrypoint
# syncs them from a Hugging Face dataset (HF_DATA_REPO + HF_TOKEN) or uses the ones mounted in /app/data.
FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.13.8 /uv /bin/uv
# libexpat is required by the GDAL bundled in the rasterio/pyogrio wheels.
RUN apt-get update && apt-get install -y --no-install-recommends libexpat1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "huggingface_hub==2.4.0"

RUN useradd -m -u 1000 user
WORKDIR /app
RUN chown user:user /app
USER user

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PORT=7860

# Dependencies first, so this layer is reused while uv.lock does not change.
COPY --chown=user:user pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=user:user src ./src
COPY --chown=user:user api ./api
COPY --chown=user:user data ./data
COPY --chown=user:user deploy/entrypoint.sh ./deploy/entrypoint.sh
RUN uv sync --frozen --no-dev
# Mount points for the data volumes, created here so they belong to user 1000.
RUN mkdir -p data/raw data/processed data/cache_contexto data/.cache

EXPOSE 7860
CMD ["sh", "deploy/entrypoint.sh"]
