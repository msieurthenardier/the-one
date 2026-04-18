FROM python:3.11-slim

# Install git, curl (health check), and fly CLI (Concourse)
RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL "http://host.docker.internal:8080/api/v1/cli?arch=amd64&platform=linux" \
       -o /usr/local/bin/fly \
    && chmod +x /usr/local/bin/fly

WORKDIR /app

COPY pyproject.toml .
COPY the_one/ the_one/
COPY tests/ tests/
COPY scripts/entrypoint.sh /entrypoint.sh

RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8484

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8484/api/info || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["the-one", "serve"]
