.PHONY: test arch-check mutation-check demo

test:
	PYTHONPATH=src python3 -m unittest discover -s tests -v

arch-check:
	python3 scripts/check_architecture.py

mutation-check:
	python3 scripts/check_failure_mutations.py

demo:
	PYTHONPATH=src python3 -m acquisition demo
