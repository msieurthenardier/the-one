FROM python:3.11-slim

# Install git, curl (healthcheck + fly CLI), ca-certificates, bubblewrap (MCP
# sandbox runtime — F3 §10), and nodejs/npm (F9 L2 D2: generic-runtime container
# for stdio MCPs invoked via `npx` — see flight 09 leg 02 §"Deliverable 2").
RUN apt-get update && apt-get install -y --no-install-recommends \
        bubblewrap \
        ca-certificates \
        curl \
        git \
        nodejs \
        npm \
        procps \
        # Playwright Chromium system deps (for visual-snapshot + flow tests
        # under tests/browser/. Without these, `playwright install chromium`
        # downloads the browser but it fails to launch with "Host system is
        # missing dependencies to run browsers").
        libxcb-dri3-0 libdrm2 libxcomposite1 libxdamage1 libxext6 \
        libxfixes3 libxrandr2 libgbm1 libcairo2 libpango-1.0-0 libasound2t64 \
        libnss3 libnspr4 libatk-bridge2.0-0t64 libatk1.0-0t64 libcups2t64 \
        libxkbcommon0 libatspi2.0-0t64 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
COPY the_one/ the_one/
COPY tests/ tests/
COPY scripts/entrypoint.sh /entrypoint.sh

# F9 L2 D2: install `uv` (provides `uvx` = `uv tool run`) and `pipx` so
# operators can declare stdio MCPs as `command=uvx args=[<pkg>]` /
# `command=pipx args=[run, <pkg>]` / `command=npx args=[-y, <pkg>]` without
# pre-baking specific MCP packages into the image. Cache directories are
# mounted as named volumes in docker-compose.yml (uv: /root/.cache/uv;
# pipx: /root/.local/share/pipx; npm: /root/.npm) so first-spawn fetches
# survive `make rebuild` cycles.
RUN pip install --no-cache-dir ".[dev,all-llms]" uv pipx

# Install Playwright Chromium browser binary (system deps already apt-installed
# above). Required by tests/browser/ — visual snapshots, flow tests, etc.
RUN playwright install chromium

EXPOSE 8484

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8484/api/info || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["the-one", "serve"]
