.PHONY: test test-shard arch-check mutation-check demo

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

BACKEND_SHARDS ?= 2

test-shard:
	PYTHONPATH=src python3 -m scripts.run_backend_shard "$(SHARD)" --shards "$(BACKEND_SHARDS)"

arch-check:
	python3 scripts/check_architecture.py

mutation-check:
	python3 scripts/check_failure_mutations.py

demo:
	PYTHONPATH=src python3 -m acquisition demo

WORKSPACE_PORT ?= 8768
WORKSPACE_ROOT ?= .local/workspace

.PHONY: workspace interface-check
workspace:
	pnpm --dir frontend install --frozen-lockfile
	pnpm --dir frontend run build
	PYTHONPATH=src python3 -m acquisition.workspace_server --port $(WORKSPACE_PORT) --root $(WORKSPACE_ROOT)

BROWSER_SHARD ?= 1
BROWSER_SHARDS ?= 1

interface-check:
	pnpm --dir frontend run build
	pnpm --dir frontend run format:check
	BROWSER_SHARD=$(BROWSER_SHARD) BROWSER_SHARDS=$(BROWSER_SHARDS) pnpm --dir frontend test
