lint:
	pylint checks.py || true

typecheck:
	mypy checks.py
