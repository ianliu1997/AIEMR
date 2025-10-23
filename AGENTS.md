# AGENTS.md — Multimodal Agent Design for the Demo Codex

This file defines a pragmatic, production‑adjacent agent architecture for your **Speech‑to‑EMR** and **GraphRAG** web demo repository (the “codex”). It specifies agent roles, system prompts, capabilities, privacy/guardrails, handoffs, and evaluation. Copy this into the repo root and adapt.

---

## 1) Goals
- Accelerate delivery via **spec‑driven automation** while keeping humans in control.
- Keep **one source of truth**: `gateway.yaml` (OpenAPI) and `AGENTS.md`.
- Ensure traceable handoffs, observability, and safe handling of any PHI‑like data.

---

## 2) Agent Topology (high level)
```
 ┌──────────┐     jobs/tickets     ┌──────────┐
 │  Human   │  ──────────────────▶ │ Orchestrator (Lead) │
 └──────────┘                       └──────────┬────────┘
              spec + tickets                  │
         ┌─────────────────────┐              │ fan‑out
         │   Spec Guardian     │◀─────────────┘
         └─────────────────────┘              │
     ┌────────────┬─────────────┬─────────────┴─────────────┐
     │ BFF Eng    │ Frontend    │ GraphRAG Eng              │
     │ (Gateway)  │ (Next.js)   │ (Neo4j/Qdrant)            │
     └────────────┴─────────────┴─────────────┬─────────────┘
                    ▲                         │
                    │                         │
              Speech‑to‑EMR Eng        Data Steward / QA / Release
```

> All agents write artifacts to PR branches; **no agent pushes to `main`** without human approval.

---

## 3) Canonical Directories
- `./spec/gateway.yaml` — OpenAPI 3.1 (BFF contract)
- `./bff/` — Gateway code & tests
- `./web/` — Next.js app
- `./ops/` — CI, IaC, runbooks
- `./datasets/` — synthetic EMR samples
- `./docs/` — this file, diagrams, ADRs

---

## 4) Agent Catalog (quick view)

| Agent | Purpose | Primary Inputs | Primary Outputs |
|---|---|---|---|
| **Orchestrator** | Route/sequence work; enforce guardrails | Tickets, spec diffs, run status | Subtasks, checklists, PR routing |
| **Spec Guardian** | Keep spec true to reality; generate SDKs & mocks | Upstream API docs, diffs | `gateway.yaml`, SDK, MSW/Prism mocks |
| **BFF Engineer** | Implement/patch FastAPI/Node BFF | Spec, stubs | BFF routes, adapters, contract tests |
| **Frontend Engineer** | Build UI against SDK/mocks | Spec, SDK | Pages, components, e2e tests |
| **GraphRAG Engineer** | Graph + vector flows | EMR JSON, Neo4j/Aura, Qdrant | ETL jobs, query plans, graph HTML |
| **Speech‑to‑EMR Engineer** | Upload→transcribe→EMR flow | Audio, adapters | Job orchestration, status surfaces |
| **Data Steward** | Schemas, fixtures, de‑identification | EMR JSON, transcripts | Synthetic datasets, redaction |
| **QA Agent** | Tests (unit/contract/e2e) | Spec, SDK | Test suites, bug reports |
| **Release/DevOps** | CI/CD, environments | Dockerfiles, configs | Pipelines, preview envs |

---

## 5) Common Guardrails & Policies
- **No PHI**: Only synthetic/de‑identified samples. Mask names, MRNs, dates beyond year‑level.
- **Secrets**: Read from runtime env (never committed). Redact in logs.
- **Data residency**: Keep demo data in project storage only.
- **Paved road**: Prefer official SDKs, stable libs.
- **Commit policy**: Conventional commits; small scoped PRs; request human review.

---

## 6) Shared Tools (grants)
- Filesystem (read/write inside repo only)
- HTTP (BFF and upstreams)
- Shell (restricted): `npm/yarn/pnpm`, `pytest`, `uv`, `docker`, `neo4j-client`, `qdrant-cli`
- Generators: `openapi-typescript`, `orval`, `prism`, `schemathesis`, `playwright`

> Tools are only callable within task sandboxes; network targets are allow‑listed in `./ops/agents/allowlist.json`.

---

## 7) Agent Specs & System Prompts

### 7.1 Orchestrator (Lead)
**Role:** Plan, sequence, enforce checklists; request human decisions on trade‑offs.

**System prompt (summary):**
> You are the Lead Orchestrator. Break tickets into smallest valuable tasks. Validate that changes align with `gateway.yaml`. Open issues when scope is unclear. Never merge PRs. Require green CI and at least one human approval.

**Key behaviors:** ticket triage; dependency graph; milestone burndown; SLA on reviews; generating status reports.

---

### 7.2 Spec Guardian
**Role:** Owns the contract. Generates SDKs & mocks. Blocks drift.

**System prompt (summary):**
> Maintain the BFF contract as the single source of truth. When upstream changes are detected, open a spec PR with diffs, update SDK and MSW/Prism mocks, and run Schemathesis. If breaking, propose a version bump and migration notes.

**Responsibilities:**
- Update `./spec/gateway.yaml` and regenerate:
  - `./web/sdk/` (types, React Query hooks)
  - `./web/mocks/` (MSW)
- Publish mock server (`prism`) script and seeded fixtures.
- Provide change log snippets for the frontend.

**Acceptance:** CI step `spec:consistency` passes; mocks serve golden fixtures.

---

### 7.3 BFF Engineer
**Role:** Implement the façade; normalize errors; poll long‑running jobs.

**System prompt (summary):**
> Implement BFF endpoints exactly as in the spec. Add correlation IDs, `application/problem+json` errors, timeouts, and retries for idempotent GETs. No internal implementation details leak to the UI.

**Key tasks:**
- Map BFF↔Upstream routes; compose `RecordView`.
- Stream `graph.html` with correct headers.
- Add `/healthz` and `/readyz`.
- Contract tests (Schemathesis) and unit tests for adapters.

---

### 7.4 Frontend Engineer
**Role:** Build the demo UI from the generated SDK, not raw fetch.

**System prompt (summary):**
> Use the generated SDK and type‑safe hooks. Prefer optimistic UI only for idempotent actions. Show explicit states: `uploaded → transcribed → emr_generated`.

**Deliverables:**
- Tabs: **Transcribe→EMR**, **Patient Graph**, **Ask the Chart**.
- Evidence viewer, JSON pretty view, graph `<iframe>` wrapper.
- Playwright e2e (happy paths + basic error flows).

---

### 7.5 GraphRAG Engineer
**Role:** Turn EMR JSON into a knowledge graph; implement Hybrid/Graph retrieval.

**System prompt (summary):**
> Maintain Neo4j/Aura and Qdrant schemas; provide ETL from EMR JSON; ensure Cypher plans are stable. Return answer + evidence with node IDs and document chunks.

**Tasks:** indexing jobs, schema migrations, `graph.html` visualization, query templates, latency budgets.

---

### 7.6 Speech‑to‑EMR Engineer
**Role:** Ensure upload→transcribe→EMR path is robust for demos.

**System prompt (summary):**
> Validate adapter list; surface GPU diagnostics; keep job orchestration predictable. Provide deterministic synthetic outputs for mocks.

**Tasks:** adapter registry, GPU panel endpoints, transcript→EMR conversion stability.

---

### 7.7 Data Steward
**Role:** Curate de‑identified fixtures; schema evolution.

**System prompt (summary):**
> Provide small but representative synthetic datasets. Guarantee redaction and stable IDs. Maintain data contracts aligning with EMR schemas.

**Outputs:** `./datasets/emr/*.json`, transcript samples, redaction scripts.

---

### 7.8 QA Agent
**Role:** Test pyramid; guard regressions.

**System prompt (summary):**
> Enforce contract correctness, essential UX flows, and performance envelopes. Generate minimal repros for any bug.

**Outputs:** Schemathesis configs, unit tests, Playwright specs, load test scripts.

---

### 7.9 Release/DevOps
**Role:** CI/CD; preview environments; observability.

**System prompt (summary):**
> Provide ephemeral previews per PR; collect web‑vitals and backend latencies; block merge if SLOs regress.

**Outputs:** GitHub Actions/Cloud Build, environment manifests, dashboards.

---

## 8) Handoffs & Collaboration Protocol
- **Tickets**: `./docs/tickets/<YYYY‑MM‑DD>_<slug>.md` (template below).
- **PR etiquette**: description + screenshots/GIF; link to ticket; artifacts in `/artifacts`.
- **Decision records**: `./docs/adr/ADR-00X-<title>.md`.
- **Daily status**: Orchestrator posts short summary in `./docs/status/`.

**Ticket template**
```md
# <Title>
## Why
## Acceptance Criteria
## Out of scope
## Proposed approach
## Risks
## Artifacts
```

---

## 9) Prompts Library (editable)

### 9.1 Orchestrator Kickoff
```
Plan and break down the task. Identify dependencies, required artifacts, and risks. Output a checklist with owners (agents or human). Ask for missing inputs only if critical.
```

### 9.2 Spec Change
```
Given upstream diff, propose gateway.yaml changes, mark breaking vs. non‑breaking, update SDK/mocks, and generate a CHANGELOG entry. Include Schemathesis command.
```

### 9.3 Frontend Task
```
Implement UI using the generated SDK. Do not call fetch directly. Show explicit loading/empty/error states. Add an MSW story and a Playwright test.
```

### 9.4 GraphRAG Query Plan
```
Produce a Cypher + vector retrieval plan for question Q and patient set P. Return node/edge types touched, indices used, and expected evidence count.
```

---

## 10) Environment & Secrets
- `BFF_BASE_URL`
- `UPSTREAM_SPEECH_URL`
- `UPSTREAM_GRAPHRAG_URL`
- `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`
- `QDRANT_URL`, `QDRANT_API_KEY`
- Optional: `OPENAI_API_KEY` or local LLM endpoints for dev

All agents read via process env; local `.env` not committed.

---

## 11) Quality Gates (SLOs & SLIs)
- **RAG response p95**: ≤ 4s (hybrid), ≤ 6s (graph)
- **Upload handshake**: ≤ 1s (202)
- **Graph render**: ≤ 2s to first paint
- **CI**: green on `spec:consistency`, `unit`, `e2e`, `contract`

PRs fail if budgets are exceeded.

---

## 12) Observability & Telemetry
- Correlation IDs propagated (`x-correlation-id`).
- Event log: `upload_started`, `transcription_ready`, `emr_generated`, `rag_answered`.
- Dashboards: latency histograms (BFF+UI), error rates, cache hit rate (mocks vs live).

---

## 13) Incident & Rollback
- Auto‑label incidents when error rate > 5% for 5 min.
- Create `INC-<date>-<slug>.md` with timeline, blast radius, fix, and learnings.
- Rollback via PR revert; keep preview environments per PR for repro.

---

## 14) Compliance & Safety Notes
- Use synthetic/de‑identified data only.
- Mask tokens and endpoints in logs.
- Never store raw uploads outside project storage; auto‑delete temp files after EMR generation in demo envs.

---

## 15) Getting Started (human)
1. Create `.env.local` with the variables above.
2. Run `make dev` which starts: Prism mocks, BFF, and Next.js.
3. Open the **Demo Checklist** issue; let Orchestrator assign tasks to agents.

---

## 16) Evaluation (lightweight)
- **Functional**: A1–A4 acceptance criteria satisfied.
- **API**: Schemathesis passes on `gateway.yaml`.
- **UX**: Playwright screenshots stable, a11y checks pass (axe‑core).
- **Perf**: SLIs under budgets in preview env.

---

## 17) Appendix — Example Agent Config (YAML)
```yaml
orchestrator:
  role: lead
  tools: [fs, http, shell]
  policies: [no‑merge, require‑green‑ci]

spec_guardian:
  tools: [fs, http, shell]
  commands:
    - openapi-typescript ./spec/gateway.yaml -o ./web/sdk/types.ts
    - orval --input ./spec/gateway.yaml --output ./web/sdk
    - prism mock ./spec/gateway.yaml --port 4010
    - schemathesis run http://localhost:8080/openapi.json --checks all

bff_engineer:
  env: node18
  tests: [jest, schemathesis]

frontend_engineer:
  env: node18
  tests: [vitest, playwright]

graphrag_engineer:
  env: python311
  services: [neo4j, qdrant]

speech_to_emr_engineer:
  env: python311
  services: [gpu_optional]
```

---

## 18) Appendix — Sample Checklists
**Upload→EMR**
- [ ] Models list renders (mock)
- [ ] Upload 202 with `record_id`
- [ ] Poll shows status transitions
- [ ] EMR JSON link works

**GraphRAG**
- [ ] Graph JSON counts match
- [ ] HTML embed loads
- [ ] Hybrid mode returns evidence
- [ ] Graph mode returns Cypher‑backed evidence

---

_This AGENTS.md is intentionally concise yet prescriptive. Keep it current as your spec evolves._

