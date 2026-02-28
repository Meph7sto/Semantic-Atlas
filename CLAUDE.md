# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Semantic-Atlas is a requirements engineering platform with AI-driven semantic analysis capabilities. The system consists of three main components:

1. **Frontend** (Vue 3 + Vite + Tailwind): Dual-mode interface with `/main` (production features) and `/alpha` (experimental AI features)
2. **Business Backend** (Flask): API orchestration, database operations, and inference proxy
3. **Inference Backend** (FastAPI): AI model serving for conflict detection, traceability, classification, and requirements extraction

## Common Commands

### Development Setup

```bash
# Install Python dependencies (requires Python 3.12 for psycopg2-binary)
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install

# Start PostgreSQL
docker compose up -d
```

### Running Services Locally

Start all three services in separate terminals:

```bash
# Terminal 1: Inference Backend (FastAPI)
uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Business Backend (Flask)
python backend_business/app.py

# Terminal 3: Frontend Dev Server
cd frontend
npm run dev
```

Access at `http://localhost:8008`

### One-Command Startup

**Linux/macOS:**
```bash
bash deploy/start.sh --mode all --provider local
bash deploy/stop_services.sh  # Stop all services
```

**Windows PowerShell:**
```powershell
.\deploy\start.ps1 -Mode all -Provider local
.\deploy\stop_services.ps1  # Stop all services
```

These scripts build the frontend, generate nginx config, and start all services with logs in `deploy/logs/`.

### Frontend Commands

```bash
cd frontend
npm run dev       # Development server (port 8008)
npm run build     # Production build
npm run preview   # Preview production build
```

## Architecture

### Port Assignment

- **8008**: Frontend (Vite dev server) or Nginx unified entry
- **5001**: Business Backend (Flask)
- **8000**: Inference Backend (FastAPI)
- **5432**: PostgreSQL
- **8080**: Adminer (database UI)

### Frontend Routing Structure

The application has three distinct routing modes managed in `App.vue`:

1. **`/guide`**: Entry point selection page (no sidebar)
2. **`/main/*`**: Production system with dedicated `Sidebar.vue` component
   - Login, Dashboard, Project Management, Requirements, Requirements Analysis
3. **`/alpha/*`**: Experimental features with inline sidebar in `App.vue`
   - Phase 1-4 pipeline (Transcript Ingestion → Context Builder → Requirements Extraction → L4 Testing)
   - Standalone features: Conflict Detection, Classification, Traceability, etc.

**Important**: When modifying sidebars:
- Main system sidebar: Edit `frontend/src/components/main/Sidebar.vue`
- Alpha system sidebar: Edit `frontend/src/components/alpha/AlphaSidebar.vue`

### API Proxy Configuration

Frontend (`vite.config.js`) proxies:
- `/api/*` → `http://localhost:5001` (Business Backend)
- `/inference/*` → `http://localhost:8000` (Inference Backend, strips `/inference` prefix)

### Backend Architecture

**Business Backend** (`backend_business/`):
- Flask app with Blueprint-based routing
- All routes except `/health` are under `/api` prefix
- Services layer handles database operations via `db_service.py` (PostgreSQL with psycopg2)
- `ai_proxy.py` forwards requests to Inference Backend

**Inference Backend** (`backend_inference/`):
- FastAPI with lifespan management for model loading
- `core/model_container.py`: Manages LLM and classification model lifecycle
- `services/`: Individual AI service implementations (conflict, traceability, classification, chat, etc.)
- Supports multiple model providers: `local`, `chutes`, `deepseek`, configurable via `.env`

### Phase 1-3 Requirements Pipeline

This is the core workflow for extracting structured requirements from meeting transcripts:

1. **Phase 1**: `/api/analysis/ingest_transcript` → Parses transcript into spans (sentences) in PostgreSQL
2. **Phase 2**: `/api/analysis/build_context` → Generates semantic bundles and context_run_id from spans
3. **Phase 3**: `/api/requirements/extract_l123` → Extracts L1/L2/L3 requirements from bundles into `requirements_l123` table

All three phases support SSE streaming variants (`/stream` endpoints) for progress updates.

## Environment Configuration

Create a `.env` file in project root. Both backends automatically load it.

### Key Variables

**Model Provider Selection**:
```bash
MODEL_PROVIDER=local|chutes|deepseek  # LLM provider
CLASSIFICATION_PROVIDER=local|remote  # Classification model provider
```

**Local Model Paths**:
```bash
LLM_MODEL_RELATIVE_PATH=data/models/deepseek_conflict
CLASSIFICATION_MODEL_RELATIVE_PATH=data/models/deberta-v3-large
```

**API Keys** (for non-local providers):
```bash
DEEPSEEK_API_KEY=your_key_here
CHUTES_API_TOKEN=your_token
CHUTES_API_KEY=your_key
OPENAI_API_KEY=your_key  # For OpenAI-compatible endpoints
```

**Database**:
```bash
DATABASE_URL=postgresql://user:pass@host:port/db  # Full connection string (preferred)
# OR individual components:
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=semantic
POSTGRES_PASSWORD=semantic_dev
POSTGRES_DB=semantic_atlas
```

**Backend URLs** (for business backend):
```bash
INFERENCE_URL=http://localhost:8000
CLASSIFICATION_URL=http://localhost:8000
```

## Database

PostgreSQL schema includes:
- `meeting_sessions`: Transcript metadata
- `meeting_spans`: Sentence-level parsed content (Phase 1)
- `context_runs`: Context build metadata (Phase 2)
- `ego_bundles`: Semantic bundles (Phase 2)
- `requirements_l123`: L1/L2/L3 extracted requirements (Phase 3)
- `trace_results`: Traceability analysis results
- `conflict_results`: Conflict detection results

Access via Adminer at `http://localhost:8080` after `docker compose up -d`.

## Key Design Patterns

### SSE Streaming Pattern

Many endpoints have streaming variants for long-running operations:
- Business backend routes: `/api/*/stream` endpoints use `yield` to proxy SSE from inference backend
- Inference backend: Async generators with `StreamingResponse` from FastAPI
- Frontend: EventSource API for consuming SSE streams

Example: `requirements/extract/stream`, `analysis/ingest_transcript/stream`, `conflict/stream_check`

### Frontend State Management

- Uses Pinia stores (not heavily utilized yet, mostly component-level state)
- API calls centralized in `frontend/src/utils/api.js` using axios
- No authentication currently (project is pre-production prototype)

### Model Loading Strategy

Inference backend uses lazy loading in `lifespan` manager:
- LLM loads via `model_engine.load_model()` supporting local/API providers
- Classification model loads separately via `classification_engine.load()`
- Knowledge Base indexes load via `kb_service.ensure_loaded()` for L4 generation
- Failures don't prevent startup; health checks pass but inference will fail

## Common Development Patterns

### Adding a New Alpha View

1. Create component in `frontend/src/views/alpha/YourFeature.vue`
2. Add route in `frontend/src/router/index.js` under `/alpha` children
3. Add navigation link in `frontend/src/components/alpha/AlphaSidebar.vue`
4. Import icon from `lucide-vue-next` in the AlphaSidebar component if needed

### Adding a New API Endpoint

**Business Backend:**
1. Create/update route file in `backend_business/routes/`
2. Register blueprint in `backend_business/app.py`
3. Use `db_service.py` for database operations
4. Forward AI requests via `ai_proxy.py` or direct requests to inference backend

**Inference Backend:**
1. Create/update router in `backend_inference/routers/`
2. Create service in `backend_inference/services/`
3. Register router in `backend_inference/main.py`
4. Use `model_engine.generate()` for LLM calls

### Testing Model Providers

Switch provider without code changes by updating `.env`:

```bash
# Test with local model
MODEL_PROVIDER=local

# Test with DeepSeek API
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key
```

Restart inference backend to pick up changes.

## Important Notes

- **Python Version**: Requires Python 3.12 for `psycopg2-binary==2.9.9` compatibility
- **Model Files**: Local model provider expects model weights in `data/models/` (not tracked in git)
- **Windows Development**: PowerShell scripts handle Nginx download automatically; use `start.ps1` with `-Provider local` for dev
- **Frontend Build**: Production build outputs to `frontend/dist/`, served by Nginx in production mode
- **CORS**: Business backend restricts to `/api/*`, inference backend allows all origins
- **JSON Encoding**: Business backend configured with `ensure_ascii=False` for proper Chinese character display

## Debugging

**Check service health:**
```bash
curl http://localhost:5001/health        # Business backend
curl http://localhost:8000/health        # Inference backend
curl http://localhost:8008/api/health    # Via frontend proxy
```

**View logs** (when using start scripts):
```bash
cat deploy/logs/business.log
cat deploy/logs/inference.log
cat deploy/logs/frontend.log
cat deploy/logs/nginx.log
```

**Database inspection:**
- Adminer UI: `http://localhost:8080`
- Direct psql: `docker exec -it semantic-atlas-postgres psql -U semantic -d semantic_atlas`
