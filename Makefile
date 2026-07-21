# vgi-xslt — dev and test targets.
#
# Usage:
#   make test       # unit/integration (pytest) + end-to-end SQL (haybarn-unittest)
#   make test-unit  # pytest only
#   make test-sql   # DuckDB sqllogictest .test files via haybarn-unittest
#
# test-sql is self-contained: it points VGI_XSLT_WORKER at the worker run as a
# uv stdio subprocess (exactly how DuckDB drives it after ATTACH) and runs the
# files under test/sql/. haybarn-unittest is a uv tool:
#   uv tool install haybarn-unittest   # installs ~/.local/bin/haybarn-unittest

# Worker command DuckDB uses for ATTACH (overridable). Drive the worker through
# the project venv's Python (the SDK installed by `uv sync`), not `uv run
# xslt_worker.py` — the latter resolves the script's PEP 723 inline deps into a
# separate, cached environment that can pin a stale vgi-python and emit an
# out-of-date catalog schema.
WORKER_STDIO    ?= .venv/bin/python xslt_worker.py

# haybarn-unittest lives in the uv tools bin; keep it on PATH.
HAYBARN_BIN     ?= $(HOME)/.local/bin
TEST_DIR         = .
TEST_PATTERN     = test/sql/*

.PHONY: test test-unit test-sql lint

test: test-unit test-sql

test-unit:
	uv run pytest -q

test-sql:
	PATH="$(HAYBARN_BIN):$$PATH" \
		VGI_XSLT_WORKER="$(WORKER_STDIO)" \
		haybarn-unittest --test-dir "$(TEST_DIR)" "$(TEST_PATTERN)"

lint:
	uv run ruff format --check .
	uv run ruff check .
	uv run mypy vgi_xslt/
