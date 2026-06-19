# the-one — local dev convenience targets.
#
# Why this file exists: the-one runs host-native via `the-one serve`
# (console script → `uvicorn.run(app, settings.host, settings.port)`).
# `make up` launches it in the background against the repo venv; `make
# restart` is how source edits take effect (the `serve` entry has no
# `--reload`). Tests spawn their own uvicorn subprocess via the conftest
# fixtures; that path is independent of the `make up` server.

.DEFAULT_GOAL := help

# ── Host interpreter ──────────────────────────────────────────────────
# Prefer the repo venv when present; fall back to bare python3.
# Override on the command line: make test PY=python3.11
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

THE_ONE_PIDFILE ?= .the-one.pid
THE_ONE_LOGFILE ?= .the-one.log

# ── App lifecycle (host-native) ───────────────────────────────────────

.PHONY: up
up: ## Start the-one host-native in the background (PID + log file)
	@if [ -f $(THE_ONE_PIDFILE) ] && kill -0 $$(cat $(THE_ONE_PIDFILE)) 2>/dev/null; then \
		echo "already running (pid $$(cat $(THE_ONE_PIDFILE)))"; exit 0; \
	fi
	@nohup $(PY) -m the_one.main serve >$(THE_ONE_LOGFILE) 2>&1 & echo $$! >$(THE_ONE_PIDFILE)
	@echo "started the-one (pid $$(cat $(THE_ONE_PIDFILE))) — log: $(THE_ONE_LOGFILE)"
	@$(MAKE) --no-print-directory verify-serving

.PHONY: down
down: ## Stop the-one (by PID)
	@if [ -f $(THE_ONE_PIDFILE) ] && kill -0 $$(cat $(THE_ONE_PIDFILE)) 2>/dev/null; then \
		kill $$(cat $(THE_ONE_PIDFILE)) && echo "stopped the-one (pid $$(cat $(THE_ONE_PIDFILE)))"; \
	else \
		echo "not running (no live pid in $(THE_ONE_PIDFILE))"; \
	fi
	@rm -f $(THE_ONE_PIDFILE)

.PHONY: restart
restart: ## Restart host-native (picks up source edits — `serve` has no --reload)
	@$(MAKE) --no-print-directory down
	@$(MAKE) --no-print-directory up

.PHONY: logs
logs: ## Follow the host log file
	@tail -f $(THE_ONE_LOGFILE)

# Internal target: install Playwright Chromium into the host Playwright cache
# (idempotent — ``playwright install chromium`` is a no-op when already present).
# Run ``make _ensure-playwright`` before browser/pixel targets.
# Note: ``playwright install-deps chromium`` requires sudo on some hosts — if
# browser tests fail with missing shared-library errors, run that command once
# manually as a host-setup prerequisite.
.PHONY: _ensure-playwright
_ensure-playwright:
	$(PY) -m playwright install chromium

.PHONY: reset-db
reset-db: ## Wipe the host data dir + restart (DESTRUCTIVE — requires CONFIRM=1)
	@if [ "$(CONFIRM)" != "1" ]; then \
		echo "✗ Refusing to wipe the data dir without CONFIRM=1"; \
		echo ""; \
		echo "  This will DELETE everything in the host data dir (settings.data_dir):"; \
		echo "    • SQLite DB (providers, agents, chat sessions, KBs, MCP sources)"; \
		echo "    • Encryption key (any backed-up encrypted API keys become unreadable)"; \
		echo "    • Knowledge base files"; \
		echo ""; \
		echo "  Re-run with: make reset-db CONFIRM=1"; \
		exit 1; \
	fi
	@$(MAKE) --no-print-directory down
	@dd=$$($(PY) -c "from the_one.config import settings; print(settings.data_dir)"); \
		echo "wiping $$dd"; rm -rf "$$dd"
	@$(MAKE) --no-print-directory up

# ── Verification ───────────────────────────────────────────────────────

.PHONY: verify-serving
verify-serving: ## Sanity-check that the host-native app serves the current source
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
	@for f in admin.js admin/system-page.js admin/providers-grid.js admin/provider-editor.js admin/provider-models.js admin/tools-form-helpers.js admin/tools-grid.js admin/tools-editor.js admin/design-language-page.js admin/design-language/tokens-section.js admin/design-language/typography-section.js admin/design-language/buttons-section.js admin/design-language/fields-section.js admin/design-language/surfaces-section.js admin/design-language/status-section.js admin/design-language/tabs-section.js admin/design-language/modal-section.js layout/section-nav.js; do \
		code=$$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8484/static/js/areas/$$f); \
		if [ "$$code" = "200" ]; then echo "  ✓ $$f served (200)"; \
		else echo "  ✗ $$f returned $$code — not serving; check 'make logs' / 'make restart'" && exit 1; fi; \
	done

# ── Brand assets ──────────────────────────────────────────────────────

.PHONY: brand-assets
brand-assets: ## Derive favicon + topbar icon PNGs from source mascot via Pillow
	$(PY) scripts/derive_brand_assets.py

# ── Tests ──────────────────────────────────────────────────────────────
# All test targets run host-native via the repo .venv (see PY variable above).

.PHONY: test
test: ## Run all default tests host-native (unit + browser; excludes -m live and -m pixel)
	PYTHON=$(PY) bash scripts/run-tests.sh tests/ -v --tb=short

.PHONY: test-unit
test-unit: ## Run unit tests only host-native (excludes browser, live, pixel)
	PYTHON=$(PY) bash scripts/run-tests.sh tests/ -m 'not browser and not live and not pixel' -v --tb=short

.PHONY: test-browser
test-browser: ## Run browser tests host-native (requires THE_ONE_DEV_MODE=true; uses Playwright)
	@$(MAKE) --no-print-directory _ensure-playwright
	PYTHON=$(PY) bash scripts/run-tests.sh -m browser tests/browser/ -v --tb=short

.PHONY: test-pixel
test-pixel: ## Run visual snapshot tests host-native (baselines gitignored — local regen only)
	@$(MAKE) --no-print-directory _ensure-playwright
	PYTHON=$(PY) bash scripts/run-tests.sh -m pixel tests/browser/ -v --tb=short

.PHONY: test-bwrap
test-bwrap: ## Run @requires_bwrap sandbox tests host-native (default-deselected; needs bwrap)
	$(PY) -m pytest -m requires_bwrap tests/ -v --tb=short

.PHONY: test-live
test-live: ## Run live-LLM tests host-native (AIAT — requires a running the-one server)
	$(PY) -m pytest -m live tests/test_aiat.py -v --tb=short

.PHONY: test-discord-hat
test-discord-hat: ## Run live multi-bot Discord HAT host-native (needs bot tokens + a test guild; SKIPs without env)
	$(PY) -m pytest -m discord_hat tests/live/discord_hat/ -v --tb=short

# ── Smoke (F9 L2 D2 generic-runtime) ──────────────────────────────────

.PHONY: smoke-runtimes
smoke-runtimes: ## Verify uvx / pipx / npx + their host caches populate and are reused (F9 L2 D2)
	bash scripts/smoke_runtime_caches.sh

# ── Code quality ───────────────────────────────────────────────────────

.PHONY: lint
lint: ## Ruff check host-native (read-only)
	$(PY) -m ruff check the_one/ tests/

.PHONY: format
format: ## Ruff format host-native (writes changes)
	$(PY) -m ruff format the_one/ tests/

.PHONY: format-check
format-check: ## Ruff format check host-native (read-only)
	$(PY) -m ruff format --check the_one/ tests/

# ── Drift detection (host-side) ────────────────────────────────────────

.PHONY: doctor
doctor:  ## Verify all declared dev extras are importable on the host venv
	@.venv/bin/python3 -c "import asgi_lifespan, pytest_asyncio, pytest_timeout, pytest_playwright, pixelmatch, pip_audit; from PIL import Image; import importlib.util; assert importlib.util.find_spec('playwright'), 'missing playwright'; import ruff; print('doctor: ok')"

.PHONY: audit
audit:  ## Run pip-audit against host venv (non-blocking; surfaces advisories)
	@.venv/bin/pip-audit --skip-editable || true

# Note: `git grep` scans the git INDEX, not the working tree — files newly added
# but unstaged won't be scanned. Run AFTER `git add` (or as part of pre-commit).
# The `:(glob)` pathspec magic is required for `**` to recurse (default fnmatch
# treats `**` literally); without it the pathspec matches nothing.
.PHONY: audit-bytes
audit-bytes:  ## Detect raw U+2028/U+2029 (LSEP/PSEP) chars in tracked .py source — must be empty (run after `git add`)
	@! git grep -lP "[\x{2028}\x{2029}]" -- ':(glob)the_one/**/*.py' ':(glob)tests/**/*.py'

# ── Help ────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@echo "the-one — local dev targets (host-native)"
	@echo ""
	@echo "Common workflow after editing JS/CSS/Python:"
	@echo "  make restart   # restart the host-native app (no --reload) + verify"
	@echo "  make logs      # tail the host log file"
	@echo "  make test      # run the test suite"
	@echo ""
	@echo "All targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'
