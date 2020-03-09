lint:
	pylint checks || true

typecheck:
	mypy checks
