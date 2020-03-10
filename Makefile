lint:
	pylint checks.py --rcfile=setup.cfg

typecheck:
	mypy checks.py --no-color-output
