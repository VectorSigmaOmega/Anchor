PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
UI_DIR := ui

.PHONY: setup dev migrate ingest test lint eval-smoke eval ui-build build deploy

setup:
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install .[dev]

dev:
	docker compose up -d postgres
	$(PYTHON) -m anchor.db.migrate
	$(PYTHON) -m uvicorn anchor.api.app:create_app --factory --reload --host 0.0.0.0 --port 8000

migrate:
	$(PYTHON) -m anchor.db.migrate

ingest:
	$(PYTHON) -m anchor.ingest.cli

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

eval-smoke:
	$(PYTHON) eval/run.py --smoke --fixture-mode

eval:
	$(PYTHON) eval/run.py

ui-build:
	cd $(UI_DIR) && npm ci && npm run build

build:
	docker build -f deploy/docker/Dockerfile -t anchor-api .

deploy:
	docker build -f deploy/docker/Dockerfile -t anchor-api .
