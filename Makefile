PYTHON ?= $(if $(wildcard .venv/bin/python),.venv/bin/python,python)
RUFF_CACHE_DIR ?= /private/tmp/arbiter-ruff-cache
PYTEST_CACHE_DIR ?= /private/tmp/arbiter-pytest-cache

.PHONY: install install-dev install-full lint test eval-dry-run app dashboard api

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev,api]"

install-full:
	$(PYTHON) -m pip install -e ".[dev,api,chromadb]"

lint:
	$(PYTHON) -m ruff check . --cache-dir $(RUFF_CACHE_DIR)

test:
	$(PYTHON) -B -m pytest --tb=short -o cache_dir=$(PYTEST_CACHE_DIR)

eval-dry-run:
	$(PYTHON) -m evals.runner --dry-run

app:
	$(PYTHON) -m streamlit run arbiter/app/streamlit_app.py

dashboard:
	$(PYTHON) -m streamlit run arbiter/app/analytics_dashboard.py

api:
	$(PYTHON) arbiter/api/run_server.py
