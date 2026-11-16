# vgi-xslt — dev and test targets. `make help` lists them. Requires uv.
#
#   make test       # unit tests (pytest) + SQL tests over stdio, launch and http
#   make test-sql   # test/sql/*.test through DuckDB (haybarn-unittest + the signed
#                   # community `vgi` extension) via ci/run-integration.sh
#   make check      # everything CI runs
#
# haybarn 2.0 is required: its community `vgi` extension speaks the worker's VGI
# protocol (vgi.v3 / 3.3). `make tools` installs the pinned runner into .tools.

HAYBARN_VERSION  ?= 2.0.0rc11
WORKER           := $(CURDIR)/.venv/bin/vgi-xslt-worker
TOOLS            := $(CURDIR)/.tools
HAYBARN_UNITTEST := $(TOOLS)/bin/haybarn-unittest
TRANSPORTS       ?= stdio launch http

build: ## Install the worker (all extras: HTTP serving needs `http`) into .venv
	uv sync --locked --all-extras

tools: ## Install the pinned SQL test runner into .tools
	@test -x $(HAYBARN_UNITTEST) || { uv venv -q $(TOOLS) && uv pip install -q -p $(TOOLS) haybarn-unittest==$(HAYBARN_VERSION); }

test-sql: build tools ## SQL tests through DuckDB over each transport: make test-sql TRANSPORTS=launch
	@set -e; for t in $(TRANSPORTS); do \
	  WORKER=$(WORKER) HAYBARN_UNITTEST=$(HAYBARN_UNITTEST) TRANSPORT=$$t ci/run-integration.sh; \
	done

test-sql-all: test-sql ## Alias: SQL tests over every transport

.DEFAULT_GOAL := help
.PHONY: help build tools test test-unit test-sql test-sql-all lint check

help: ## List the targets
	@awk 'BEGIN{FS=":.*## "} /^[a-zA-Z_-]+:.*## /{printf "  %-14s %s\n",$$1,$$2}' $(MAKEFILE_LIST)

test-unit: build ## Unit tests (pytest)
	uv run pytest -q

test: test-unit test-sql ## Unit + SQL tests

check: lint test ## Everything CI runs

lint: ## Static checks: ruff, mypy
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy vgi_xslt/
