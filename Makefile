.PHONY: test arch-check mutation-check demo

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

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

interface-check:
	pnpm --dir frontend run build
	pnpm --dir frontend run format:check
	pnpm --dir frontend test
