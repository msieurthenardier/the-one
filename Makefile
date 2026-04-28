# the-one — local dev convenience targets.
#
# Why this file exists: the Dockerfile `COPY the_one/` bakes JS/CSS/Python
# into the image at build time. Editing source on the host does NOT update
# the running container at port 8484 — `make rebuild` is required for
# changes to surface. (The `/workspace` bind-mount is used by tests which
# spawn their own uvicorn subprocess; it does NOT feed the served app.)

.DEFAULT_GOAL := help

# ── Container lifecycle ────────────────────────────────────────────────

.PHONY: up
up: ## Start the-one (no rebuild)
	docker compose up -d the-one

.PHONY: down
down: ## Stop the-one
	docker compose down

.PHONY: rebuild
rebuild: ## Rebuild image + restart (REQUIRED after editing JS/CSS/Python)
	docker compose build the-one
	docker compose up -d the-one
	@$(MAKE) --no-print-directory _ensure-playwright
	@$(MAKE) --no-print-directory verify-serving

.PHONY: rebuild-clean
rebuild-clean: ## Rebuild image + wipe DB volume + restart fresh (HAT prep, no confirm gate)
	docker compose down
	docker volume rm -f the-one_the_one_data
	docker compose build the-one
	docker compose up -d the-one
	@$(MAKE) --no-print-directory _ensure-playwright
	@$(MAKE) --no-print-directory verify-serving

# Internal target: reinstall playwright browsers + system deps if missing.
# Cache lives at /root/.cache/ms-playwright inside the container, which does
# NOT persist across `docker compose down` / image rebuilds — without this,
# every rebuild leaves the test suite unable to launch chromium.
.PHONY: _ensure-playwright
_ensure-playwright:
	@if ! docker exec the-one test -x /root/.cache/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-linux64/chrome-headless-shell 2>/dev/null; then \
		echo "Installing playwright chromium (cache was wiped by rebuild) ..."; \
		docker exec the-one playwright install chromium >/dev/null 2>&1; \
		docker exec the-one playwright install-deps chromium >/dev/null 2>&1; \
		echo "  ✓ playwright chromium ready"; \
	fi

.PHONY: reset-db
reset-db: ## Wipe DB volume + restart (DESTRUCTIVE — requires CONFIRM=1)
	@if [ "$(CONFIRM)" != "1" ]; then \
		echo "✗ Refusing to wipe DB without CONFIRM=1"; \
		echo ""; \
		echo "  This will DELETE everything in /root/.the-one inside the container:"; \
		echo "    • SQLite DB (providers, agents, chat sessions, KBs, MCP sources)"; \
		echo "    • Encryption key (any backed-up encrypted API keys become unreadable)"; \
		echo "    • Knowledge base files"; \
		echo ""; \
		echo "  Re-run with: make reset-db CONFIRM=1"; \
		exit 1; \
	fi
	docker compose down
	docker volume rm -f the-one_the_one_data
	docker compose up -d the-one
	@$(MAKE) --no-print-directory verify-serving

.PHONY: restart
restart: ## Restart container without rebuilding (picks up env var changes only)
	docker compose restart the-one

.PHONY: logs
logs: ## Follow container logs
	docker compose logs -f the-one

.PHONY: shell
shell: ## Open a bash shell inside the container
	docker exec -it the-one bash

# ── Verification ───────────────────────────────────────────────────────

.PHONY: verify-serving
verify-serving: ## Sanity-check that the running container serves the current source
	@echo "Waiting for http://localhost:8484/api/info to come up (max 30s) ..."
	@for i in $$(seq 1 30); do \
		if curl -fsS http://localhost:8484/api/info >/dev/null 2>&1; then \
			echo "  ✓ /api/info OK (after $${i}s)"; break; \
		fi; \
		if [ "$$i" = "30" ]; then \
			echo "  ✗ /api/info did not respond within 30s — check 'make logs'"; exit 1; \
		fi; \
		sleep 1; \
	done
	@echo "Verifying admin sub-modules served ..."
	@for f in admin.js admin/system-page.js admin/providers-grid.js admin/provider-editor.js admin/provider-models.js layout/section-nav.js; do \
		code=$$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8484/static/js/areas/$$f); \
		if [ "$$code" = "200" ]; then echo "  ✓ $$f served (200)"; \
		else echo "  ✗ $$f returned $$code — image may be stale, run 'make rebuild'" && exit 1; fi; \
	done

# ── Tests ──────────────────────────────────────────────────────────────

.PHONY: test
test: ## Run all default tests (unit + browser; excludes -m live and -m pixel)
	docker exec the-one pytest tests/ -v --tb=short

.PHONY: test-unit
test-unit: ## Run unit tests only (excludes browser, live, pixel)
	docker exec the-one pytest tests/ -m 'not browser and not live and not pixel' -v --tb=short

.PHONY: test-browser
test-browser: ## Run browser tests (requires THE_ONE_DEV_MODE=true; uses Playwright)
	docker exec the-one pytest -m browser tests/browser/ -v --tb=short

.PHONY: test-pixel
test-pixel: ## Run visual snapshot tests (baselines are gitignored — local regen only)
	docker exec the-one pytest -m pixel tests/browser/ -v --tb=short

.PHONY: test-live
test-live: ## Run live-LLM tests (AIAT — requires running provider)
	docker exec the-one pytest -m live tests/test_aiat.py -v --tb=short

# ── Code quality ───────────────────────────────────────────────────────

.PHONY: lint
lint: ## Ruff check (read-only)
	docker exec the-one ruff check the_one/ tests/

.PHONY: format
format: ## Ruff format (writes changes)
	docker exec the-one ruff format the_one/ tests/

# ── Help ────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@echo "the-one — local dev targets"
	@echo ""
	@echo "Common workflow after editing JS/CSS/Python:"
	@echo "  make rebuild   # rebuild image + restart + verify"
	@echo "  make logs      # tail logs"
	@echo "  make test      # run the test suite"
	@echo ""
	@echo "All targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
