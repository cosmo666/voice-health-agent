.PHONY: setup run-api run-agent run-frontend run-all test seed clean

# Detect OS for venv path
ifeq ($(OS),Windows_NT)
    VENV_BIN = .venv/Scripts
    PYTHON = python
else
    VENV_BIN = .venv/bin
    PYTHON = python3
endif

setup:           ## One-time: create venv, install deps, setup DB, seed data, install frontend
	$(PYTHON) -m venv .venv
	$(VENV_BIN)/pip install -r requirements.txt
	cd frontend && npm install
	$(VENV_BIN)/python scripts/setup_db.py
	$(VENV_BIN)/python scripts/seed_data.py
	$(VENV_BIN)/python scripts/seed_knowledge_base.py

run-api:         ## Start FastAPI backend on port 8000
	$(VENV_BIN)/uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

run-agent:       ## Start Pipecat voice agent with WebRTC UI on port 7860
	$(VENV_BIN)/uvicorn agent.main:app --host 0.0.0.0 --port 7860

run-frontend:    ## Start React dev server on port 3000
	cd frontend && npm run dev

run-all:         ## Start all 3 services in background (use separate terminal tabs)
	@echo "Open 3 terminal tabs and run:"
	@echo "  Tab 1: make run-api"
	@echo "  Tab 2: make run-agent"
	@echo "  Tab 3: make run-frontend"

test:            ## Run pytest suite
	$(VENV_BIN)/pytest tests/ -v

seed:            ## Re-seed database and knowledge base
	$(VENV_BIN)/python scripts/seed_data.py
	$(VENV_BIN)/python scripts/seed_knowledge_base.py

clean:           ## Remove DB, ChromaDB data, venv
	rm -f clinic.db
	rm -rf chroma_db/
	rm -rf .venv/
	rm -rf frontend/node_modules/
