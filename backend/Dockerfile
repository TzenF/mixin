# Une seule base de code, deux images :
#   docker build --target api    -> API FastAPI (légère)
#   docker build --target worker -> worker d'analyse (avec Essentia, x86_64 uniquement)

FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app

FROM base AS api
RUN pip install ".[dev]"
COPY tests ./tests
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
RUN pip install ".[worker]"
CMD ["arq", "app.worker.main.WorkerSettings"]
