lint:
	@pylint checks --rcfile=setup.cfg

typecheck:
	@mypy checks --no-color-output
