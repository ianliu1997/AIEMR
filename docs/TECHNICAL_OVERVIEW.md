# AIEMR Demo – Technical Overview

## 1. Purpose
The AIEMR demo showcases a unified experience for two previously separate systems:

- **Speech-to-EMR** – processes clinical audio uploads into validated transcripts and structured EMR JSON artifacts.
- **GraphRAG Chatbot** – ingests EMR JSON into a knowledge graph/vector store and answers clinician questions using hybrid retrieval.

This document captures the current architecture, critical flows, dependencies, and operational considerations so new contributors can onboard quickly and extend the platform safely.

Canonical sources of truth:
- API contract: `spec/gateway.yaml`
- Agent operating model: `AGENTS.md`
- Gateway BFF: `bff/`
- Next.js demo UI: `web/`

## 2. High-Level Architecture
```
 ┌────────┐        ┌───────────────────────────┐
 │  Web   │  HTTPS │  FastAPI Gateway (bff/app) │
 └────────┘ ◀─────▶└────────────┬──────────────┘
                                 │ orchestrates
                 ┌───────────────┴──────────────┐
                 │                              │
        Speech-to-EMR API              GraphRAG API
  (AIEMR_system/speech2emr/app)   (AIEMR_system/chatbot_rag/app)
                 │                              │
           SQLite + Files                Neo4j + Qdrant
                 │                              │
             EMR JSON ───────────────────────────┘
```

- The **FastAPI gateway** exposes a stable BFF contract, handles correlation IDs, and adapts legacy service responses into a single frontend-friendly shape.
- **Speech-to-EMR** persists jobs in SQLite (`patient_record` table), stores artifacts under `uploads/`, `transcripts/`, `emr/`, and triggers background Whisper + EMR conversion pipelines.
- **GraphRAG** ingests EMR JSON into Neo4j and Qdrant, exposes graph visualization and hybrid retrieval endpoints.
- The **Next.js UI** calls only through the generated SDK, presenting three tabs: upload pipeline, graph viewer, and RAG chat.

## 3. Request Flows

### 3.1 Speech-to-EMR pipeline
1. User uploads a WAV file via `POST /v1/speech/jobs`.
2. Gateway writes to `uploads/`, creates a `patient_record` row, and schedules `run_transcription_simple`.
3. ASR runs with the selected adapter, writes transcript to `transcripts/transcript_{id}.txt`, updates DB status.
4. EMR conversion (`emr.service.build_and_store_emr`) produces JSON under `emr/emr_{id}.json`, status becomes `emr_generated`.
5. Client polls `GET /v1/speech/jobs`, `GET /v1/speech/jobs/{id}`, and downloads artifacts via dedicated endpoints.

### 3.2 Graph ingest + chat
1. Gateway triggers `POST /v1/rag/ingest/sync` → `sync_once` scans EMR JSON directory, creates/updates patient subgraphs in Neo4j and vectors in Qdrant.
2. `GET /v1/rag/patients` enumerates patients with graph availability, node/edge counts, last ingest time.
3. `GET /v1/rag/patients/{id}/graph` returns node/edge data; `/graph-html` streams PyVis HTML for iframe embedding.
4. `POST /v1/rag/query` runs hybrid (graph + vector) retrieval; `POST /v1/rag/query-with-document` enriches context with an uploaded text document.

## 4. Components

### 4.1 Gateway (`bff/app`)
- `main.py`: FastAPI app, lifespan bootstrapping, correlation ID middleware, Problem+JSON error handler.
- Routers:
  - `routers/health.py`: `/healthz`, `/readyz` with dependency probes.
  - `routers/speech.py`: adapters, job CRUD, transcript/EMR download.
  - `routers/rag.py`: sync trigger, graph metadata, RAG queries.
- Services:
  - `services/speech.py`: serializes `PatientRecord` rows into contract-compliant payloads.
  - `services/rag.py`: wraps Neo4j/Qdrant helpers, HTML rendering, answer formatting.
- Dependencies:
  - `dependencies.py` reuses sessions/drivers from the legacy services while guaranteeing consistency.

### 4.2 Speech-to-EMR (`AIEMR_system/speech2emr/`)
- `app/main.py`: original FastAPI service used by the gateway; retained for background work.
- `simple_models.py` & `simple_crud.py`: normalized single-table schema (`patient_record`) with status transitions `uploaded → transcribed → emr_generated`.
- `asr.py`, `model_registry.py`: Medical Whisper integrations with optional LoRA adapters.
- `emr/service.py`: GPT-based EMR synthesis, GPU memory management, checksum metadata.
- Storage layout:
  - `uploads/` – raw WAV files.
  - `transcripts/` – plain-text transcripts.
  - `emr/` – structured EMR JSON output.
  - `patient.db` – SQLite database accessed via SQLModel.

### 4.3 GraphRAG (`AIEMR_system/chatbot_rag/`)
- `app/graph/ingest.py`: schema enforcement (`SCHEMA`), EMR JSON loader, Neo4j ingestion, checksum metadata.
- `app/services/syncer.py`: periodic filesystem watcher that triggers ingestion + Qdrant upserts.
- `app/services/retriever.py`: hybrid answer pipeline combining nearest-neighbour chunks with graph facts.
- `app/services/graphrag.py`: LangChain-backed Cypher QA chain for graph-mode queries.
- `app/services/visualize.py`: NetworkX + PyVis graph renderer.
- Depends on Neo4j, Qdrant, and OpenAI-compatible models for embeddings/chat.

### 4.4 Frontend (`web/`)
- Generated SDK (`sdk/`) mirrors `spec/gateway.yaml`, wraps fetch with correlation IDs, typed responses, and React Query hooks.
- Components:
  - `SpeechUploadForm`, `SpeechJobsPanel` – upload UX and status timeline with transcript/EMR preview.
  - `GraphViewer` – patient selector and iframe graph embed.
  - `RagChat` – hybrid/graph mode question form with optional doc upload & evidence display.
- App shell uses Next.js App Router with `QueryClientProvider` for caching/polling.
- Global styles emphasize clear state transitions and tabbed navigation.

## 5. Data & Storage
- **SQLite (`patient.db`)**: `patient_record` table stores job metadata, artifact file IDs, timezone metadata, adapter key, status, timestamps.
- **Filesystem**: `uploads/`, `transcripts/`, `emr/` are shared between speech and GraphRAG ingestion.
- **Neo4j**: Patient → Section → Schema → Value graph, plus `IngestionMeta` nodes to track file hashes.
- **Qdrant**: Vector store keyed by patient for ANN retrieval; collection name defaults to `patient_transcript`.
- **Static graph HTML**: `AIEMR_system/chatbot_rag/static/graphs/` holds PyVis outputs.

## 6. API Contract
- Defined in `spec/gateway.yaml` (OpenAPI 3.1). Key models: `SpeechJob`, `SpeechAdapter`, `GraphResponse`, `RagAnswer`.
- Contract expectations:
  - All responses include `x-correlation-id`.
  - Error format follows `application/problem+json`.
  - Transcript/EMR endpoints return `202` until artifacts are ready.
- Regenerate SDK: `npm run spec:types` inside `web/`.

## 7. Configuration

### Gateway (`bff/app/config.py`)
- `GATEWAY_ALLOWED_ORIGINS` – CORS whitelist for the frontend.
- `GATEWAY_REQUEST_TIMEOUT_SECONDS` – request timeout budget.

### Speech-to-EMR
- `STT_MODEL_NAME`, `STT_ADAPTERS_DIR`, `DEFAULT_ADAPTER`.
- `EMR_DIR`, `UPLOAD_DIR`, `TRANSCRIPT_DIR`.
- `DB_URL` (defaults to `sqlite:///./patient.db`).
- GPU guards (see `gpu_monitor.py`).

### GraphRAG
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASS`.
- `QDRANT_URL`, `QDRANT_API_KEY`, `QDRANT_COLLECTION`.
- `OPENAI_API_KEY`, `EMBED_MODEL`, `CHAT_MODEL`.
- `EMR_DIR` (points at the same EMR JSON directory as speech service).

Provide these via `.env` during development; never commit live secrets.

## 8. Local Development
1. **Backend**  
   ```bash
   cd bff
   pip install -r requirements.txt
   uvicorn app.main:app --reload --port 8080
   ```
   Ensure underlying services can access SQLite/EMR directories; populate `.env` with Neo4j/Qdrant/OpenAI stubs or local endpoints.

2. **Frontend**  
   ```bash
   cd web
   npm install
   npm run dev
   ```
   Configure `NEXT_PUBLIC_GATEWAY_BASE_URL=http://localhost:8080`. Optionally enable MSW mocks for UI-only demos.

3. **External services**  
   - Neo4j + Qdrant must be reachable from the gateway for RAG operations.
   - Run periodic sync manually via `POST /v1/rag/ingest/sync` if background ingestion is disabled.

## 9. Observability & Guardrails
- Gateway injects `x-correlation-id` on every request and propagates it downstream; log correlation IDs in service logs for tracing.
- GPU health endpoints remain in the speech service (`/gpu-status`, `/gpu-cleanup`) for diagnostics.
- Ingestion metadata tracks file hashes to avoid duplicate graph loads.
- `AGENTS.md` establishes non-functional policies: no PHI, redaction, paved-road tooling, CI gates.

## 10. Security & Privacy
- All datasets must be synthetic/de-identified. Production PHI is out of scope.
- Secrets live in environment variables; do not check in credentials.
- Uploaded audio and generated EMR files stay inside project storage; automate cleanup for demo environments after EMR generation.

## 11. Testing & Quality
- Current baseline: Python `compileall` sanity check (`python3 -m compileall bff`), React Query polling, TypeScript strict mode.
- Future enhancements:
  - Contract tests via Schemathesis (`spec:consistency` CI gate).
  - Playwright flows covering upload, graph view, QA.
  - Unit tests for `services/speech.py` serialization and `services/rag.py` answer shaping.

## 12. Deployment Notes
- Gateway can be containerized alongside the legacy services or serve as a façade deployed separately with upstream base URLs.
- Enable HTTPS termination at the edge, enforce CORS whitelist, rate limit uploads.
- Monitor SLOs defined in `AGENTS.md` (upload handshake ≤1s, RAG p95 ≤6s, etc.).
- Provide CI steps for `spec:consistency`, `unit`, `e2e`, `contract` before allowing merges.

## 13. Open Questions / Follow-ups
- Integrate Celery or async task queue if transcription/EMR workloads need to scale beyond single-node background tasks.
- Formalize Neo4j/Qdrant mocks or local stacks for contributors without cloud resources.
- Add detailed GPU telemetry (per adapter) surfaced via the gateway for the UI.

---
For clarifications or design changes, update this document alongside `AGENTS.md` to keep the project’s source of truth consistent.
