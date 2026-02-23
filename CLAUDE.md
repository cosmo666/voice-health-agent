# CLAUDE.md

## Project Overview
Build a production-grade **Voice AI Agent** for healthcare appointment booking. Patients talk to "Maya" (AI receptionist) via browser WebRTC. She books/cancels appointments, answers clinic FAQs via RAG, and escalates to humans. Open-source stack, optimized for developer machine.

## Hardware Constraints (CRITICAL — READ FIRST)
- **16GB RAM, NO GPU** — this is the target machine
- **LLM runs via Ollama Cloud models** (free tier) — NOT locally. Do NOT load any LLM into local RAM
- STT uses `faster-whisper` with **`base.en`** model (CPU-optimized, ~150MB RAM) — NOT large-v3
- TTS uses Kokoro-82M with **ONNX runtime on CPU** (~200MB RAM)
- Silero VAD runs on CPU (~50MB)
- **Total AI model RAM budget: ~500MB** — rest for SQLite, ChromaDB, Python services, frontend dev server
- Do NOT use `device="cuda"` anywhere — always `device="cpu"` or `compute_type="int8"`
- **NO Daily.co** — use SmallWebRTCTransport (free, P2P, no API key)

## Hard Rules
- Python 3.11, async/await everywhere
- Must run on 16GB RAM, CPU-only machine
- **NO Docker** — all services run directly on the host machine via process managers / terminal tabs
- Every file: type hints, docstrings, loguru logging, error handling
- No `# TODO`, no `pass` placeholders — implement everything fully
- No notebook-style code — production patterns only
- Use SQLite instead of PostgreSQL (zero setup, single file DB, perfect for POC)
- Use Python's built-in asyncio or background threads instead of Celery+Redis (removes 2 heavy dependencies)

## Tech Stack (DO NOT SUBSTITUTE)

### Voice Pipeline — REAL-TIME CONVERSATIONAL (this is the core of the project)
- `pipecat-ai[silero,smallwebrtc]` — orchestration (Apache 2.0)
- **SmallWebRTCTransport** — FREE peer-to-peer WebRTC, NO API keys, NO Daily.co account needed
  - Uses `aiortc` under the hood for P2P audio streaming
  - Built-in development runner with prebuilt web UI: `pipecat-ai-small-webrtc-prebuilt`
  - The runner serves a web page at http://localhost:7860 where user clicks "Connect" and talks
- Silero VAD — voice activity detection (MIT, CPU-only, ~50MB)
- **SmartTurn v3** — AI-powered turn detection (knows when user is done talking vs just pausing)
- `faster-whisper>=1.1.0` — STT (MIT, CTranslate2) — **USE `base.en` model, `compute_type="int8"`** for CPU
- `kokoro>=0.9.4` — TTS, 82M params (Apache 2.0) — **USE ONNX runtime on CPU**
- **Interruption handling ENABLED** — user can interrupt Maya mid-sentence, just like a real conversation
- **NO Daily.co** — SmallWebRTCTransport is fully local, zero external dependencies

### Real-Time Conversation Requirements (CRITICAL)
The voice interaction MUST feel like a real phone call:
1. **Turn-based flow**: User speaks → Maya responds → User speaks → Maya responds (natural back-and-forth)
2. **Interruptions**: If user starts talking while Maya is speaking, Maya STOPS immediately and listens
3. **Smart turn detection**: Use `LocalSmartTurnAnalyzerV3` — AI model that detects if user is done talking or just pausing mid-sentence. Do NOT use simple silence timeout alone.
4. **No awkward silences**: Maya should respond within 1-2 seconds of user finishing their turn
5. **Streaming TTS**: Maya's speech should start playing as soon as the first audio chunk is ready, NOT wait for the full response to generate
6. **Filler words**: Maya says brief acknowledgments ("Got it", "One moment") while waiting for slow operations like API calls
7. **VAD config**: `stop_secs=0.5` (tight but not jumpy), `start_secs=0.2`, `confidence=0.7`

### LLM — Ollama Cloud (gpt-oss:20b-cloud) — OpenAI's open-weight model
- Model: **`gpt-oss:20b-cloud`** — ONLY this model, NO fallbacks, NO alternatives
- OpenAI's open-weight 20B param model, Apache 2.0, near GPT-4o quality
- Native function calling, chain-of-thought reasoning, structured outputs
- Runs on Ollama cloud GPUs — zero local RAM for model weights
- Ollama is already installed on host machine — NO API key needed, NO `ollama login` needed
- Access via standard Ollama API: `http://localhost:11434`
- Also compatible with OpenAI SDK: `base_url="http://localhost:11434/v1"`, `api_key="ollama"`
- IMPORTANT: gpt-oss does tool calling as part of chain-of-thought (CoT) — return reasoning back in subsequent tool call responses

### RAG
- LlamaIndex + ChromaDB + sentence-transformers (**all-MiniLM-L6-v2**, ~90MB, CPU)

### Backend
- FastAPI + SQLAlchemy 2.0 async + **SQLite** (aiosqlite) + Alembic + Pydantic v2
- SQLite = zero setup, single file `clinic.db`, perfect for POC
- NO PostgreSQL, NO Docker needed

### Async Processing
- **asyncio background tasks** (FastAPI BackgroundTasks + asyncio.create_task)
- NO Celery, NO Redis — too heavy for a POC on 16GB, adds unnecessary complexity

### Observability
- LangFuse (self-hosted, `pip install langfuse`) + MLflow (local, `pip install mlflow`) + Ragas
- NO Prometheus, NO Grafana — overkill for local POC. Use LangFuse dashboard + MLflow UI instead

### Dashboard — React + shadcn/ui (NOT Streamlit)
- React 18 + TypeScript + Vite — fast modern frontend
- shadcn/ui — polished component library (Radix UI primitives + Tailwind CSS)
- TanStack Query (React Query) — server state management, auto-refetch
- Recharts — charts library (built on D3, works with shadcn/ui)
- Tailwind CSS 3 — utility-first styling
- The dashboard is a separate `frontend/` directory with its own package.json
- Communicates with FastAPI backend via REST API
- Must be production-quality: responsive, dark mode support, loading states, error boundaries

### Infra
- **NO Docker** — everything runs directly on host
- Loguru for logging
- `Makefile` with targets to start/stop all services
- Python venv for backend, Node for frontend
- SQLite DB file in project root (no database server to manage)

---

## Project Structure

```
voice-health-agent/
├── CLAUDE.md                           # This file
├── .env.example                        # All env vars with defaults
├── .gitignore
├── README.md                           # Setup guide + architecture
├── requirements.txt                    # Pinned Python deps
├── Makefile                            # setup, run, test, seed, clean, dev
│
├── agent/                              # Pipecat Voice Agent
│   ├── __init__.py
│   ├── main.py                         # FastAPI app: SmallWebRTC prebuilt UI + /api/offer endpoint
│   ├── pipeline.py                     # VAD → STT → LLM → TTS pipeline
│   ├── prompts.py                      # Maya's system prompt + escalation keywords
│   ├── tools.py                        # 5 function schemas + async executors
│   ├── flows.py                        # State machine: greeting→intent→action→confirm→farewell
│   └── config.py                       # Pydantic BaseSettings
│
├── api/                                # FastAPI Backend
│   ├── __init__.py
│   ├── main.py                         # App with CORS, lifespan, health check
│   ├── database.py                     # Async SQLite engine via aiosqlite
│   ├── models.py                       # SQLAlchemy models
│   ├── schemas.py                      # Pydantic request/response models
│   ├── dependencies.py                 # DB session injection
│   ├── background.py                   # Async background tasks (replaces Celery)
│   └── routes/
│       ├── __init__.py
│       ├── appointments.py             # CRUD: check_slots, book, cancel, reschedule
│       ├── doctors.py                  # List, filter by specialty
│       ├── patients.py                 # Lookup/create by phone
│       └── calls.py                    # Call logs + transcripts
│
├── rag/                                # RAG Knowledge Base
│   ├── __init__.py
│   ├── ingest.py                       # Markdown → chunk → embed → ChromaDB
│   ├── query_engine.py                 # LlamaIndex query with Ollama synthesis
│   ├── evaluate.py                     # Ragas eval on 20 test questions
│   └── documents/                      # Realistic healthcare content
│       ├── insurance_policies.md       # 5 plans with copays, coverage
│       ├── clinic_services.md          # 15+ services with descriptions
│       ├── doctor_profiles.md          # 8 doctors with specialties
│       ├── patient_faq.md              # 30+ Q&A pairs
│       └── clinic_policies.md          # Hours, cancellation, COVID, parking
│
├── frontend/                           # React + shadcn/ui Admin Dashboard
│   ├── package.json                    # React 18, TypeScript, Vite, shadcn/ui, TanStack Query
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   ├── components.json                 # shadcn/ui config
│   ├── index.html
│   └── src/
│       ├── main.tsx                    # App entry point
│       ├── App.tsx                     # Router + layout (sidebar nav)
│       ├── lib/
│       │   ├── api.ts                  # Axios/fetch client for FastAPI backend
│       │   └── utils.ts               # shadcn/ui cn() utility
│       ├── hooks/
│       │   ├── use-calls.ts            # TanStack Query hooks for call logs
│       │   ├── use-analytics.ts        # TanStack Query hooks for analytics data
│       │   └── use-config.ts           # Hook for agent config CRUD
│       ├── components/
│       │   └── ui/                     # shadcn/ui components (auto-generated)
│       │       ├── button.tsx
│       │       ├── card.tsx
│       │       ├── table.tsx
│       │       ├── input.tsx
│       │       ├── badge.tsx
│       │       ├── dialog.tsx
│       │       ├── textarea.tsx
│       │       ├── select.tsx
│       │       ├── tabs.tsx
│       │       ├── skeleton.tsx
│       │       └── sidebar.tsx
│       ├── pages/
│       │   ├── DashboardPage.tsx       # Overview: key metrics cards, recent calls
│       │   ├── CallLogsPage.tsx        # Searchable table, click to expand transcript
│       │   ├── AnalyticsPage.tsx       # 6 Recharts charts (calls/day, booking rate, etc.)
│       │   └── AgentConfigPage.tsx     # Live prompt editor + system health status
│       └── styles/
│           └── globals.css             # Tailwind base + shadcn/ui theme
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                     # Fixtures: test SQLite DB, test client, mock Ollama
│   ├── test_api.py                     # All endpoint tests
│   ├── test_tools.py                   # Tool function unit tests
│   ├── test_rag.py                     # RAG retrieval accuracy tests
│   └── test_models.py                  # DB model relationship tests
│
├── alembic/
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       └── 001_initial.py              # All tables migration
│
└── scripts/
    ├── setup_db.py                     # Create tables + run migrations
    ├── seed_data.py                    # 8 doctors, 50+ slots, 5 patients
    ├── seed_knowledge_base.py          # Ingest docs into ChromaDB
    └── benchmark_latency.py            # Measure voice round-trip time
```

---

## Database Schema

```sql
-- Doctor: id (UUID PK), name, specialty, bio, available_days (JSON array), consultation_fee (decimal), created_at
-- Patient: id (UUID PK), name, phone (unique indexed), email, insurance_provider, date_of_birth, created_at
-- TimeSlot: id (UUID PK), doctor_id (FK→Doctor), slot_date (date), start_time (time), end_time (time), is_available (bool default true)
-- Appointment: id (UUID PK), patient_id (FK→Patient), doctor_id (FK→Doctor), slot_id (FK→TimeSlot unique), visit_type (enum: general/followup/specialist/urgent), status (enum: scheduled/cancelled/completed/no_show), notes (text nullable), created_at, updated_at
-- CallLog: id (UUID PK), patient_phone, duration_seconds (int), transcript (text), summary (text nullable), tools_used (JSON array), escalated (bool default false), sentiment_score (float nullable), created_at
```

## API Endpoints

```
GET  /health                                    → {"status": "ok", "services": {...}}
GET  /api/appointments/slots?doctor_name=&visit_type=&date=  → available slots
POST /api/appointments/                         → book (creates patient if new)
DELETE /api/appointments/?patient_phone=&reason= → cancel
PUT  /api/appointments/{id}/reschedule          → move to new slot
GET  /api/appointments/?patient_phone=          → patient's appointments
GET  /api/doctors/                              → all doctors
GET  /api/doctors/?specialty=                   → filter by specialty
GET  /api/patients/?phone=                      → lookup patient
POST /api/patients/                             → create patient
GET  /api/rag/query?q=                          → RAG answer + sources
POST /api/calls/                                → save call log
GET  /api/calls/?page=&per_page=&phone=         → paginated call logs
GET  /api/calls/{id}                            → call detail
```

## LLM Tool Definitions (5 tools, OpenAI function-calling format)

1. **check_available_slots**(doctor_name: str, visit_type: str, preferred_date: str|null) → GET /api/appointments/slots
2. **book_appointment**(patient_name: str, patient_phone: str, doctor_name: str, slot_datetime: str, visit_type: str, notes: str|null) → POST /api/appointments/
3. **cancel_appointment**(patient_phone: str, reason: str|null) → DELETE /api/appointments/
4. **search_clinic_info**(query: str) → GET /api/rag/query
5. **escalate_to_human**(reason: str, urgency: "low"|"medium"|"high"|"emergency", summary: str) → log + TTS message

Each tool: async httpx call to FastAPI backend, structured JSON response back to LLM.

## Voice Pipeline Flow — Real-Time Conversation

```
User opens http://localhost:7860 in browser → clicks "Connect"
  → SmallWebRTCTransport establishes P2P WebRTC audio stream (no server needed)
  → Maya greets: "Hi, this is Maya at Sunrise Health Clinic. How can I help you today?"

REAL-TIME CONVERSATION LOOP:
  User speaks → Silero VAD detects speech start → marks "user is talking"
    → SmartTurn v3 AI model monitors: is user done or just pausing?
    → User stops → SmartTurn confirms turn is complete
    → Faster-Whisper base.en transcribes audio to text (CPU, int8, ~500-800ms)
    → gpt-oss:20b-cloud processes with system prompt + tools (streaming response)
      → If tool_call: execute async → inject filler "One moment..." → feed result back → get answer
    → Kokoro-82M streams speech audio chunks back immediately (don't wait for full text)
    → User hears Maya responding in real-time

  IF USER INTERRUPTS (starts talking while Maya is speaking):
    → VAD detects new speech → Pipecat CANCELS current TTS output immediately
    → Audio playback STOPS → pipeline switches to listening mode
    → Conversation context is trimmed to what user actually heard (word-level alignment)
    → New user input is processed normally

Target: <1500ms voice-to-voice latency (user stops speaking → first audio of Maya's response)
```

## Pipecat Pipeline Configuration (agent/pipeline.py)

```python
from pipecat.transports.services.small_webrtc import SmallWebRTCTransport
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.turn.smart_turn.local_smart_turn_v3 import LocalSmartTurnAnalyzerV3
from pipecat.turns.user_stop import TurnAnalyzerUserTurnStopStrategy

# Transport — FREE P2P WebRTC, no API keys
transport = SmallWebRTCTransport(
    webrtc_connection=webrtc_connection,
    params=TransportParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        vad_enabled=True,
        vad_analyzer=SileroVADAnalyzer(
            params=VADParams(
                stop_secs=0.5,       # Responsive but not jumpy
                start_secs=0.2,
                confidence=0.7,
                min_volume=0.6,
            )
        ),
        turn_stop_strategy=TurnAnalyzerUserTurnStopStrategy(
            turn_analyzer=LocalSmartTurnAnalyzerV3()  # AI-powered turn detection
        ),
    ),
)

# STT — CPU optimized
stt = FasterWhisperSTTService(
    model_size="base.en",
    device="cpu",
    compute_type="int8",
    language="en",
)

# TTS — CPU, streaming output
tts = KokoroTTSService(
    voice="af_bella",
    speed=1.0,
)

# LLM — gpt-oss:20b-cloud via Ollama (ONLY this model, no fallbacks)
llm = OllamaLLMService(
    model="gpt-oss:20b-cloud",
    base_url="http://localhost:11434",
)

# Pipeline: transport.input → VAD → STT → LLM (with tools) → TTS → transport.output
# Interruptions are handled automatically by Pipecat when VAD detects new speech during TTS output
```

## Agent Runner (agent/main.py)

```python
from pipecat_ai_small_webrtc_prebuilt.frontend import SmallWebRTCPrebuiltUI
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

app = FastAPI()

# Serve the built-in WebRTC UI at /
app.mount("/client", SmallWebRTCPrebuiltUI)

@app.get("/")
async def root():
    return RedirectResponse(url="/client/")

# POST /api/offer — SmallWebRTCTransport P2P signaling endpoint
@app.post("/api/offer")
async def offer(request: Request):
    # Create pipeline, handle WebRTC offer/answer exchange
    ...

# Run with: uvicorn agent.main:app --host 0.0.0.0 --port 7860
```

## Conversation State Machine (flows.py)

```
GREETING → (detect intent) → BOOKING_FLOW | FAQ_FLOW | ESCALATION | FAREWELL
BOOKING_FLOW → COLLECT_INFO → CHECK_SLOTS → CONFIRM_BOOKING → FAREWELL
FAQ_FLOW → RAG_QUERY → ANSWER → (follow-up?) → FAREWELL
ESCALATION → NOTIFY_PATIENT → LOG_ESCALATION → FAREWELL
10s silence timeout → prompt user "Are you still there?"
```

## System Prompt for Maya (agent/prompts.py)

Maya is a warm, professional virtual receptionist at Sunrise Health Clinic. She:
- Greets patients by name if recognized by phone
- Books, reschedules, cancels appointments
- Answers insurance, services, hours, policies questions via RAG
- Uses SHORT sentences (voice-friendly, 1-2 sentences max per turn)
- Always confirms before taking actions ("I have Thursday at 2:30 with Dr. Patel — shall I book that?")
- Escalates when: patient mentions chest pain/emergency, is very frustrated, asks for human, topic is billing dispute
- Never gives medical advice
- Speaks naturally with filler acknowledgments ("Got it", "Sure thing", "Of course")

## Seed Data Requirements

**8 Doctors:** Dr. Sarah Patel (Cardiology), Dr. James Wilson (General), Dr. Priya Sharma (Pediatrics), Dr. Michael Chen (Dermatology), Dr. Emily Rodriguez (OB-GYN), Dr. David Kim (Orthopedics), Dr. Aisha Hassan (Internal Medicine), Dr. Robert Thompson (ENT)

**50+ Time Slots:** Spread across next 2 weeks, Mon-Fri 9am-5pm (30-min slots), some pre-booked

**5 Sample Patients:** With realistic names, phone numbers, insurance providers

## RAG Document Requirements

All documents must contain realistic, detailed healthcare content. Insurance docs must include actual copay amounts ($20-$50), deductible ranges ($500-$3000), coverage percentages. FAQ must cover 30+ real questions patients ask.

## Running Locally (NO Docker)

**All services run directly on your machine. No Docker, no containers.**

### Prerequisites (already installed):
- Python 3.11
- Node.js 20+
- Ollama (already installed, no API key needed)

### One-time setup:
```bash
# Pull cloud model (just metadata, no big download)
ollama pull gpt-oss:20b-cloud

# Python venv
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt

# Install espeak-ng (needed by Kokoro TTS)
sudo apt-get install espeak-ng   # Linux
# brew install espeak            # Mac

# Frontend
cd frontend && npm install && cd ..

# Setup DB + seed data
python scripts/setup_db.py
python scripts/seed_data.py
python scripts/seed_knowledge_base.py
```

### Makefile targets:
```makefile
.PHONY: setup run-api run-agent run-frontend run-all test seed clean

setup:           ## One-time: create venv, install deps, setup DB, seed data, install frontend
	python -m venv .venv
	.venv/bin/pip install -r requirements.txt
	cd frontend && npm install
	.venv/bin/python scripts/setup_db.py
	.venv/bin/python scripts/seed_data.py
	.venv/bin/python scripts/seed_knowledge_base.py

run-api:         ## Start FastAPI backend on port 8000
	.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

run-agent:       ## Start Pipecat voice agent with WebRTC UI on port 7860
	.venv/bin/uvicorn agent.main:app --host 0.0.0.0 --port 7860

run-frontend:    ## Start React dev server on port 3000
	cd frontend && npm run dev

run-all:         ## Start all 3 services in background (use separate terminal tabs)
	@echo "Open 3 terminal tabs and run:"
	@echo "  Tab 1: make run-api"
	@echo "  Tab 2: make run-agent"
	@echo "  Tab 3: make run-frontend"

test:            ## Run pytest suite
	.venv/bin/pytest tests/ -v

seed:            ## Re-seed database and knowledge base
	.venv/bin/python scripts/seed_data.py
	.venv/bin/python scripts/seed_knowledge_base.py

clean:           ## Remove DB, ChromaDB data, venv
	rm -f clinic.db
	rm -rf chroma_db/
	rm -rf .venv/
	rm -rf frontend/node_modules/
```

### Running (3 terminal tabs):
```bash
# Terminal 1 — FastAPI backend
make run-api                     # http://localhost:8000

# Terminal 2 — Voice agent + WebRTC UI
make run-agent                   # http://localhost:7860 ← open this in browser, click Connect, start talking!

# Terminal 3 — React admin dashboard
make run-frontend                # http://localhost:3000
```

### How to use the voice agent:
1. Start all 3 services (see above)
2. Open **http://localhost:7860** in Chrome (needs microphone access)
3. Click **"Connect"** button
4. Maya greets you — start talking naturally
5. It's a real-time conversation: you talk → Maya responds → you talk → Maya responds
6. Try: "I'd like to book an appointment with Dr. Patel" or "What insurance do you accept?"

### Database:
- **SQLite** — single file `clinic.db` in project root
- Zero setup, no server process, no password
- Async via `aiosqlite` driver
- `database.py` uses: `sqlite+aiosqlite:///./clinic.db`

### Background tasks (replaces Celery+Redis):
- **`api/background.py`** — uses FastAPI's `BackgroundTasks` + `asyncio.create_task()`
- Post-call processing (summary generation, sentiment) runs as async background tasks
- No external task queue needed

## Monitoring (Lightweight — no Prometheus/Grafana)

- **LangFuse** (`pip install langfuse`): trace every LLM call with input/output/latency/tokens. Access via LangFuse cloud free tier or self-hosted
- **MLflow** (`pip install mlflow`): experiment tracking, prompt version management. Run with `mlflow ui` on port 5000
- Built-in logging via Loguru — structured JSON logs for all services
- **Latency targets for real-time conversation (CPU + cloud LLM):**
  - STT (Faster-Whisper base.en CPU): ~500-800ms per utterance
  - LLM (gpt-oss:20b-cloud via Ollama): ~300-600ms (network + inference)
  - TTS first audio chunk (Kokoro CPU streaming): ~200-400ms
  - **Total voice-to-voice target: <1500ms** (user stops talking → first audio of Maya's response)
  - Industry benchmark: 500-1500ms is considered good for voice agents

## Test Requirements

- test_api.py: test every endpoint (happy path + error cases), use httpx AsyncClient
- test_tools.py: mock httpx calls, verify tool functions return correct schemas
- test_rag.py: ingest test docs, verify retrieval returns relevant chunks
- test_models.py: verify FK relationships, cascade deletes, unique constraints
- conftest.py: async SQLite in-memory DB (`sqlite+aiosqlite:///:memory:`), mock Ollama with fixed responses, test ChromaDB collection

## Build Order

1. Project skeleton (dirs, __init__.py files, .env.example, requirements.txt, Makefile, .gitignore)
2. api/ (database.py [SQLite+aiosqlite] → models.py → schemas.py → dependencies.py → background.py → routes/ → main.py)
3. rag/ (documents/ content → ingest.py → query_engine.py → evaluate.py)
4. agent/ (config.py → prompts.py → tools.py → pipeline.py → flows.py → main.py)
5. frontend/ (Vite + React + TypeScript + shadcn/ui + TanStack Query + Recharts)
   - Initialize with: `npm create vite@latest frontend -- --template react-ts`
   - Install shadcn/ui: `npx shadcn@latest init` then add components
   - Install: `@tanstack/react-query`, `recharts`, `react-router-dom`, `axios`
   - Build pages: DashboardPage → CallLogsPage → AnalyticsPage → AgentConfigPage
   - Use shadcn/ui components: Card, Table, Badge, Dialog, Tabs, Skeleton, Sidebar
   - Dark mode support via shadcn/ui theme toggle
   - All API calls via TanStack Query with loading/error states
6. tests/ (conftest.py → test_models.py → test_api.py → test_tools.py → test_rag.py)
7. scripts/ (setup_db.py → seed_data.py → seed_knowledge_base.py → benchmark_latency.py)
8. alembic/ setup
9. README.md (full documentation with `make setup` + `make run-all` quick start)