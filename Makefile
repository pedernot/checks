lint:
	pylint checks.py --rcfile=setup.cfg || true

typecheck:
	mypy checks.py --no-color-output
