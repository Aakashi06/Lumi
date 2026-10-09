.PHONY: setup backend frontend models test build benchmark
setup:
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt
	backend/.venv/bin/python -m spacy download en_core_web_sm
	cd frontend && npm ci
backend:
	backend/.venv/bin/uvicorn lumi.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
frontend:
	cd frontend && npm run dev
models:
	./scripts/models.sh
test:
	backend/.venv/bin/python -m pytest -q
build:
	cd frontend && npm run build

benchmark:
	backend/.venv/bin/python scripts/benchmark.py --output benchmarks/after.json
