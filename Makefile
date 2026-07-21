.PHONY: install dev test lint

install:
	python -m pip install -e '.[dev]'

dev:
	uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

test:
	pytest

lint:
	ruff check app tests
