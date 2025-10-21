# ---- gateway ---------------------------------------------------------------
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# minimal system deps
RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      libmagic1 poppler-utils ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# deps layer (cache)
COPY requirements.txt .
RUN python -m pip install --upgrade pip wheel && \
    pip install --no-cache-dir -r requirements.txt

# source
COPY . .

EXPOSE 8080
# Note: compose provides --reload for dev and no-proxy for prod
CMD ["uvicorn","apps.gateway.main:app","--host","0.0.0.0","--port","8080"]
