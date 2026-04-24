FROM python:3.11-slim

# Install git and curl (health check + fly CLI download at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY the_one/ the_one/
COPY tests/ tests/
COPY scripts/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir ".[dev,all-llms]"

EXPOSE 8484

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8484/api/info || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["the-one", "serve"]
