# Voice Health Agent -- AI-Powered Healthcare Receptionist

**Maya** is an AI-powered voice receptionist for **Sunrise Health Clinic**. Patients
talk to Maya through their browser via WebRTC, and she handles appointment booking,
cancellations, rescheduling, insurance questions, and clinic FAQs -- all through
natural, real-time voice conversation.

Built entirely with open-source tools, runs on a 16GB RAM CPU-only machine with
no Docker required.

---

## Architecture

The system is composed of three independently running services that communicate
over HTTP and WebRTC:

```
                         +-------------------------------------------+
                         |             Patient's Browser              |
                         |  (Chrome -- microphone + WebRTC audio)     |
                         +------------------+------------------------+
                                            |
                              WebRTC P2P Audio Stream
                              (SmallWebRTCTransport)
                                            |
   +----------------------------------------v-----------------------------------------+
   |                        VOICE AGENT  (port 7860)                                   |
   |                                                                                   |
   |   Mic Audio --> Silero VAD --> SmartTurn v3 --> Faster-Whisper STT (base.en)       |
   |       |                                              |                            |
   |       |                                         [transcript]                      |
   |       |                                              |                            |
   |       |                                    gpt-oss:20b-cloud (Ollama)             |
   |       |                                      |               |                    |
   |       |                                [text response]  [tool_calls]              |
   |       |                                      |               |                    |
   |       |                              Kokoro TTS (82M)   HTTP calls --------+      |
   |       |                                      |                             |      |
   |       +<-- Audio out (streaming) <-----------+                             |      |
   +---------------------------------------------------------------------------|------+
                                                                                |
                                                                                v
   +---------------------------------------------------------------------------|------+
   |                        API BACKEND  (port 8000)                            |      |
   |                                                                            |      |
   |   /api/appointments/*    /api/doctors/*    /api/patients/*                 |      |
   |   /api/calls/*           /api/rag/query    /health                         |      |
   |                                                                            |      |
   |   SQLite (clinic.db) <-- SQLAlchemy 2.0 async (aiosqlite)                 |      |
   |   ChromaDB (chroma_db/) <-- LlamaIndex + sentence-transformers            |      |
   +---------------------------------------------------------------------------|------+
                                                                                |
   +---------------------------------------------------------------------------|------+
   |                     ADMIN DASHBOARD  (port 3000)                           |      |
   |                                                                                   |
   |   React 18 + TypeScript + Vite + shadcn/ui + TanStack Query + Recharts            |
   |                                                                                   |
   |   Pages: Dashboard | Call Logs | Analytics | Agent Config                         |
   +-----------------------------------------------------------------------------------+
```

---

## Tech Stack

| Layer          | Technology                                             | License     |
|----------------|--------------------------------------------------------|-------------|
| Voice Pipeline | Pipecat (SmallWebRTCTransport + Silero VAD)            | Apache 2.0  |
| Turn Detection | SmartTurn v3 (AI-powered)                              | Apache 2.0  |
| STT            | Faster-Whisper `base.en` (CPU, int8)                   | MIT         |
| TTS            | Kokoro-82M (ONNX, CPU)                                 | Apache 2.0  |
| LLM            | gpt-oss:20b-cloud via Ollama                           | Apache 2.0  |
| RAG            | LlamaIndex + ChromaDB + all-MiniLM-L6-v2              | MIT/Apache  |
| API            | FastAPI + SQLAlchemy 2.0 async + SQLite                | MIT/BSD     |
| Frontend       | React 18 + TypeScript + Vite + shadcn/ui               | MIT         |
| Observability  | LangFuse + MLflow                                      | MIT/Apache  |
| Logging        | Loguru                                                 | MIT         |

---

## Quick Start

### Prerequisites

- **Python 3.11+** (with `pip`)
- **Node.js 20+** (with `npm`)
- **Ollama** (installed and running -- no API key needed)
- **espeak-ng** (required by Kokoro TTS)
  - Windows: download from [espeak-ng releases](https://github.com/espeak-ng/espeak-ng/releases)
  - Linux: `sudo apt-get install espeak-ng`
  - macOS: `brew install espeak`

### One-Time Setup

```bash
# Clone the repository
git clone https://github.com/your-org/voice-health-agent.git
cd voice-health-agent

# Pull the cloud LLM model (metadata only, no large download)
ollama pull gpt-oss:20b-cloud

# Run the full setup (venv, deps, DB, seed data, frontend)
make setup
```

Or step by step:

```bash
# 1. Create Python virtual environment and install dependencies
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r requirements.txt

# 2. Install frontend dependencies
cd frontend && npm install && cd ..

# 3. Create database tables
python scripts/setup_db.py

# 4. Seed sample data (doctors, patients, time slots)
python scripts/seed_data.py

# 5. Ingest RAG knowledge base documents
python scripts/seed_knowledge_base.py
```

### Running the Application

Open **three terminal tabs** and start each service:

```bash
# Terminal 1 -- FastAPI Backend (port 8000)
make run-api

# Terminal 2 -- Voice Agent + WebRTC UI (port 7860)
make run-agent

# Terminal 3 -- React Admin Dashboard (port 3000)
make run-frontend
```

### Using the Voice Agent

1. Ensure all three services are running
2. Open **http://localhost:7860** in Google Chrome
3. Allow microphone access when prompted
4. Click the **"Connect"** button
5. Maya greets you -- start talking naturally

**Try these phrases:**
- "I'd like to book an appointment with Dr. Patel"
- "What insurance plans do you accept?"
- "Can I cancel my appointment?"
- "What are your clinic hours?"
- "I need to see a dermatologist next week"

### Admin Dashboard

Open **http://localhost:3000** to access the admin dashboard with:
- **Dashboard**: Overview metrics, recent calls, active appointments
- **Call Logs**: Searchable/filterable table of all voice interactions
- **Analytics**: Charts for call volume, booking rates, sentiment trends
- **Agent Config**: Live system prompt editor and service health monitor

---

## Project Structure

```
voice-health-agent/
|-- CLAUDE.md                       # AI assistant instructions
|-- README.md                       # This file
|-- .env.example                    # Environment variables template
|-- .gitignore                      # Git ignore rules
|-- requirements.txt                # Python dependencies (pinned)
|-- Makefile                        # Build/run/test targets
|-- alembic.ini                     # Alembic migration config
|
|-- agent/                          # Pipecat Voice Agent
|   |-- __init__.py
|   |-- main.py                     # FastAPI app: WebRTC UI + /api/offer
|   |-- pipeline.py                 # VAD -> STT -> LLM -> TTS pipeline
|   |-- prompts.py                  # Maya's system prompt
|   |-- tools.py                    # 5 LLM function-calling tools
|   |-- flows.py                    # Conversation state machine
|   +-- config.py                   # Pydantic settings
|
|-- api/                            # FastAPI REST Backend
|   |-- __init__.py
|   |-- main.py                     # App with CORS, lifespan, health
|   |-- database.py                 # Async SQLite engine (aiosqlite)
|   |-- models.py                   # SQLAlchemy ORM models
|   |-- schemas.py                  # Pydantic request/response models
|   |-- dependencies.py             # DB session dependency injection
|   |-- background.py               # Async background tasks
|   +-- routes/
|       |-- __init__.py
|       |-- appointments.py         # Booking CRUD
|       |-- doctors.py              # Doctor listings
|       |-- patients.py             # Patient lookup/create
|       +-- calls.py                # Call log CRUD
|
|-- rag/                            # RAG Knowledge Base
|   |-- __init__.py
|   |-- ingest.py                   # Markdown -> chunk -> embed -> ChromaDB
|   |-- query_engine.py             # LlamaIndex query with Ollama
|   |-- evaluate.py                 # Ragas evaluation
|   +-- documents/
|       |-- insurance_policies.md   # 5 insurance plans with copays
|       |-- clinic_services.md      # 15+ services with descriptions
|       |-- doctor_profiles.md      # 8 doctor bios
|       |-- patient_faq.md          # 30+ Q&A pairs
|       +-- clinic_policies.md      # Hours, cancellation, parking
|
|-- frontend/                       # React Admin Dashboard
|   |-- package.json
|   |-- vite.config.ts
|   |-- tailwind.config.ts
|   +-- src/
|       |-- main.tsx                # Entry point
|       |-- App.tsx                 # Router + sidebar layout
|       |-- lib/
|       |   |-- api.ts              # HTTP client for backend
|       |   +-- utils.ts            # shadcn/ui utilities
|       |-- hooks/
|       |   |-- use-calls.ts        # TanStack Query: call logs
|       |   |-- use-analytics.ts    # TanStack Query: analytics
|       |   +-- use-config.ts       # TanStack Query: agent config
|       |-- components/ui/          # shadcn/ui components
|       |-- pages/
|       |   |-- DashboardPage.tsx   # Key metrics + recent calls
|       |   |-- CallLogsPage.tsx    # Searchable call log table
|       |   |-- AnalyticsPage.tsx   # 6 Recharts visualizations
|       |   +-- AgentConfigPage.tsx # Prompt editor + health status
|       +-- styles/
|           +-- globals.css         # Tailwind + shadcn/ui theme
|
|-- tests/                          # Test suite
|   |-- __init__.py
|   |-- conftest.py                 # Fixtures: in-memory DB, mocks
|   |-- test_api.py                 # Endpoint tests
|   |-- test_tools.py               # Tool function tests
|   |-- test_rag.py                 # RAG retrieval tests
|   +-- test_models.py              # DB model tests
|
|-- alembic/                        # Database migrations
|   |-- env.py                      # Async migration environment
|   +-- versions/
|       +-- 001_initial.py          # Initial schema
|
+-- scripts/                        # Utility scripts
    |-- setup_db.py                 # Create tables
    |-- seed_data.py                # Seed doctors, slots, patients
    |-- seed_knowledge_base.py      # Ingest docs into ChromaDB
    +-- benchmark_latency.py        # Measure pipeline latencies
```

---

## API Documentation

The FastAPI backend serves a Swagger UI at **http://localhost:8000/docs** when
running. All endpoints are listed below.

### Health

| Method | Path      | Description                          |
|--------|-----------|--------------------------------------|
| GET    | `/health` | Service health check (API, DB, Ollama) |

### Appointments

| Method | Path                              | Description                        |
|--------|-----------------------------------|------------------------------------|
| GET    | `/api/appointments/slots`         | Available slots (filter by doctor, date, type) |
| POST   | `/api/appointments/`              | Book an appointment                |
| GET    | `/api/appointments/`              | List appointments (filter by phone) |
| DELETE | `/api/appointments/`              | Cancel appointment by phone        |
| PUT    | `/api/appointments/{id}/reschedule` | Reschedule to a new slot         |

### Doctors

| Method | Path             | Description                       |
|--------|------------------|-----------------------------------|
| GET    | `/api/doctors/`  | List all doctors (filter by specialty) |

### Patients

| Method | Path              | Description                      |
|--------|-------------------|----------------------------------|
| GET    | `/api/patients/`  | Lookup patient by phone          |
| POST   | `/api/patients/`  | Register a new patient           |

### RAG

| Method | Path              | Description                      |
|--------|-------------------|----------------------------------|
| GET    | `/api/rag/query`  | Answer clinic questions via RAG  |

### Call Logs

| Method | Path              | Description                      |
|--------|-------------------|----------------------------------|
| POST   | `/api/calls/`     | Save a call log                  |
| GET    | `/api/calls/`     | Paginated call logs (filter by phone) |
| GET    | `/api/calls/{id}` | Single call log detail           |

---

## Voice Pipeline

The voice interaction follows a real-time conversational loop:

```
User opens browser  -->  clicks "Connect"
  |
  v
SmallWebRTCTransport establishes P2P WebRTC audio stream
  |
  v
Maya greets: "Hi, this is Maya at Sunrise Health Clinic..."
  |
  v
+---------------------------------------------------------------+
|                   REAL-TIME CONVERSATION LOOP                 |
|                                                               |
|  User speaks                                                  |
|    |-> Silero VAD detects speech start                        |
|    |-> SmartTurn v3 monitors: done talking or just pausing?   |
|    |-> User stops -> SmartTurn confirms turn complete          |
|    |-> Faster-Whisper base.en transcribes (~500-800ms)        |
|    |-> gpt-oss:20b-cloud processes with tools (streaming)     |
|    |     |-> If tool_call: execute async, say "One moment..." |
|    |     |-> Feed result back -> get final answer             |
|    |-> Kokoro-82M streams TTS audio chunks immediately        |
|    |-> User hears Maya responding in real-time                |
|                                                               |
|  IF USER INTERRUPTS (starts talking while Maya speaks):       |
|    |-> VAD detects new speech                                 |
|    |-> Pipecat CANCELS current TTS output immediately         |
|    |-> Pipeline switches to listening mode                    |
|    |-> New user input processed normally                      |
+---------------------------------------------------------------+

Target: <1500ms voice-to-voice latency
  STT:  ~500-800ms  (Faster-Whisper base.en, CPU, int8)
  LLM:  ~300-600ms  (gpt-oss:20b-cloud via Ollama)
  TTS:  ~200-400ms  (Kokoro-82M ONNX, CPU, streaming)
```

---

## LLM Tools

Maya has access to five function-calling tools:

| Tool                      | Description                                    |
|---------------------------|------------------------------------------------|
| `check_available_slots`   | Query available appointment slots by doctor/date |
| `book_appointment`        | Book an appointment (creates patient if new)   |
| `cancel_appointment`      | Cancel an existing appointment by phone        |
| `search_clinic_info`      | Search the RAG knowledge base for clinic info  |
| `escalate_to_human`       | Escalate to a human agent with reason/urgency  |

---

## Database

The application uses **SQLite** via the `aiosqlite` async driver. The database
file is stored at `clinic.db` in the project root. No database server process
is required.

### Schema

- **doctors** -- 8 physicians with specialties, bios, availability, fees
- **patients** -- registered patients with phone (unique key), insurance
- **time_slots** -- 30-minute appointment windows per doctor per day
- **appointments** -- booked visits linking patient + doctor + slot
- **call_logs** -- voice call transcripts, summaries, sentiment scores

### Migrations

Alembic is configured for async SQLite migrations:

```bash
# Run pending migrations
alembic upgrade head

# Generate a new migration after model changes
alembic revision --autogenerate -m "description"

# Rollback one migration
alembic downgrade -1
```

---

## Development

### Running Tests

```bash
make test
# or directly:
pytest tests/ -v
```

Tests use an in-memory SQLite database and mock external services (Ollama,
ChromaDB) so they run fast without requiring any services to be up.

### Re-Seeding Data

```bash
make seed
# or:
python scripts/seed_data.py
python scripts/seed_knowledge_base.py
```

The seed scripts are idempotent -- they check for existing data before
inserting and skip if records already exist.

### Benchmarking Latency

With the API and Ollama running:

```bash
python scripts/benchmark_latency.py
```

This benchmarks each pipeline component and prints a results table with
min/avg/max/p95 latencies alongside the target thresholds.

### Clean Slate

```bash
make clean
```

Removes `clinic.db`, `chroma_db/`, `.venv/`, and `frontend/node_modules/`.

### Environment Variables

Copy `.env.example` to `.env` and customize as needed:

```bash
cp .env.example .env
```

Key variables:

| Variable               | Default                            | Description              |
|------------------------|------------------------------------|--------------------------|
| `DATABASE_URL`         | `sqlite+aiosqlite:///./clinic.db`  | SQLAlchemy database URL  |
| `OLLAMA_BASE_URL`      | `http://localhost:11434`           | Ollama API endpoint      |
| `OLLAMA_MODEL`         | `gpt-oss:20b-cloud`               | LLM model tag            |
| `WHISPER_MODEL`        | `base.en`                          | Faster-Whisper model     |
| `KOKORO_VOICE`         | `af_bella`                         | TTS voice preset         |
| `LOG_LEVEL`            | `INFO`                             | Loguru log level         |
| `LANGFUSE_PUBLIC_KEY`  | *(empty)*                          | LangFuse key (optional)  |

---

## Observability

### LangFuse

Traces every LLM call with input, output, latency, and token counts. Set
`LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` in `.env` to enable. Access
via the LangFuse cloud free tier or self-host with:

```bash
pip install langfuse
```

### MLflow

Tracks prompt versions and experiment metrics. Launch the UI with:

```bash
mlflow ui --port 5000
```

Then open **http://localhost:5000** in your browser.

### Logging

All services use Loguru with structured, colorized output to stderr. Log
level is controlled by the `LOG_LEVEL` environment variable.

---

## Hardware Requirements

This project is optimized for a developer machine with:

- **16 GB RAM** (no GPU required)
- **CPU-only inference** for all AI models

Approximate memory usage:

| Component                    | RAM     |
|------------------------------|---------|
| Faster-Whisper base.en (int8)| ~150 MB |
| Kokoro-82M TTS (ONNX)       | ~200 MB |
| Silero VAD                   | ~50 MB  |
| sentence-transformers        | ~90 MB  |
| SQLite + ChromaDB            | ~50 MB  |
| Python services + frontend   | ~500 MB |
| **Total**                    | **~1 GB** |

The LLM (gpt-oss:20b-cloud) runs on Ollama's cloud infrastructure and
consumes zero local RAM for model weights.

---

## License

MIT
