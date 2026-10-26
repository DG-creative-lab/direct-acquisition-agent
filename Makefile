.PHONY: test arch-check mutation-check demo

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

arch-check:
	python3 scripts/check_architecture.py

mutation-check:
	python3 scripts/check_failure_mutations.py

demo:
	PYTHONPATH=src python3 -m acquisition demo

.PHONY: workspace interface-check
workspace:
	npm --prefix frontend ci
	npm --prefix frontend run build
	PYTHONPATH=src python3 -m acquisition.workspace_server

interface-check:
	npm --prefix frontend run build
	npm --prefix frontend run format:check
