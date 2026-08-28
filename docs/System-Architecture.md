# System Architecture Document
## AskYourData.ai

**Version:** 1.0

---

## 1. Architectural Goals

1. Correctness and safety of generated queries before execution.
2. Strict multi-tenant workspace isolation.
3. Replaceability of the LLM provider and the execution backend.
4. Minimizing LLM calls where a deterministic path suffices.
5. Full observability and auditability of every query and data access.

---

## 2. High-Level Component Diagram

```text
                         ┌─────────────────────┐
                         │      Frontend        │
                         │  React / Next.js     │
                         └──────────┬───────────┘
                                    │ REST/JSON (TLS)
                         ┌──────────▼───────────┐
                         │        API Gateway     │
                         │  Auth · Rate Limiting  │
                         └──────────┬───────────┘
                                    │
        ┌───────────────┬──────────┼───────────┬───────────────┐
        │               │          │           │               │
  ┌─────▼─────┐   ┌─────▼─────┐┌───▼────┐ ┌────▼─────┐  ┌──────▼──────┐
  │ Ingestion │   │  Catalog  ││  Query  │ │  Cache   │  │ Observability│
  │  Service  │   │  Service  ││ Pipeline│ │ (Redis)  │  │ / Audit Log  │
  └─────┬─────┘   └─────┬─────┘└───┬────┘ └──────────┘  └─────────────┘
        │               │          │
        │         ┌─────▼─────┐    │
        │         │ Supabase  │    │
        │         │  (PG+RLS) │    │
        │         └───────────┘    │
        │                          │
  ┌─────▼─────┐            ┌───────▼────────┐
  │ File/Job   │            │  LLM Provider  │
  │  Queue +   │            │  Abstraction   │
  │  Workers   │            │     Layer      │
  └─────┬─────┘            └───────┬────────┘
        │                          │
  ┌─────▼─────┐            ┌───────▼────────┐
  │ Supabase   │            │  Provider A/B/C │
  │ Storage    │            │  (interchangeable)│
  └───────────┘             └────────────────┘
        │
  ┌─────▼──────────────────────────────┐
  │        Execution Layer               │
  │  DuckDB · Pandas (sandboxed) ·       │
  │  External SQL DBs (read-only)        │
  └───────────────────────────────────────┘
```

---

## 3. Component Descriptions

### 3.1 API Gateway
Handles request routing and the first layer of rate limiting. Authentication itself is delegated to **Supabase Auth** — the frontend obtains a session directly from Supabase (email/password, OIDC/SAML), and the gateway's job is only to verify the resulting Supabase-issued JWT (against Supabase's public JWKS) on every request, then resolve the caller's role for the target workspace. All downstream services receive an authenticated `user_id` + `workspace_id` + role context — never re-derive identity downstream.

### 3.2 Ingestion Service
Validates uploaded files, stores raw files in Supabase Storage, and either processes synchronously (small files) or enqueues a job (large files). Emits parsed schema/statistics to the Catalog Service and PII findings for tagging.

### 3.3 Catalog Service
Owns the Data Catalog: schemas, statistics, semantic types, PII tags, relationships, dataset versions, and the semantic layer (metrics/dimensions). Backed by Supabase (PostgreSQL) with row-level security scoping every row to `workspace_id`.

### 3.4 Query Pipeline (core)
Orchestrates: request validation → rate limiting → cache lookup → deterministic routing check → schema retrieval → disambiguation → LLM query planning (via abstraction layer) → Query IR → validation → execution → result validation → answer generation → visualization selection. Stateless service, horizontally scalable; conversation context persisted externally (Postgres/Redis), not in-process.

### 3.5 LLM Provider Abstraction Layer
```text
interface LLMProvider {
  generate(purpose: Purpose, input: StructuredInput, schema: OutputSchema): StructuredOutput
}
```
* One adapter per vendor (e.g. Anthropic, OpenAI, local model) implementing the same interface.
* A `ProviderRouter` selects the active provider per purpose (configurable, supports A/B and failover).
* All prompt templates are versioned and stored outside vendor-specific code, so template changes do not require redeploying adapters and vice versa.
* Every output is schema-validated before leaving this layer — nothing downstream ever sees an unvalidated LLM response.
* A `DeterministicPlanner` component implements the same interface for the query types identified in SRS FR-NLQ-4, allowing those requests to bypass the LLM entirely while still flowing through the same pipeline shape.

### 3.6 Execution Layer
* **DuckDB** — default engine for file-based data (CSV/Excel/Parquet), run in-process or in a dedicated execution service.
* **External SQL** — native drivers (read-only credentials only) for Postgres/MySQL/SQL Server.
* **Pandas** — sandboxed execution path (separate container/process with CPU/memory/timeout/import/network restrictions) compiled from the same Query IR.
* A `BackendCompiler` per engine translates the versioned Query IR into the engine's native query — this is the seam that keeps the pipeline backend-agnostic.

### 3.7 Cache Layer (Redis)
Query-plan and result caches keyed by `workspace_id + dataset_version + normalized_question + permissions`. Live-DB entries carry TTL and are invalidated on schema-drift detection (a background job periodically diffs connected-DB schemas against the last cataloged version).

### 3.8 Job Queue & Workers
Handles async file ingestion, scheduled schema refresh for connected databases, and scheduled cache-invalidation checks. Decouples heavy processing from the request/response path.

### 3.9 Observability & Audit
* **LLM usage log** — every LLM call with cost/latency/tokens (feeds cost dashboards).
* **Request trace log** — full pipeline trace per `request_id` (feeds debugging/observability dashboards).
* **Audit log** — durable, append-only record of security-relevant actions (auth, connection, upload, query execution, membership/role changes), independent of whether an LLM was involved (feeds compliance reporting).

---

## 4. Data Flow — Natural Language Query (sequence)

```text
User → API Gateway: POST /query {workspace_id, question, thread_id?}
API Gateway → Query Pipeline: forward w/ user/role context
Query Pipeline → Rate Limiter: check limits
Query Pipeline → Cache: lookup(normalized_question, dataset_version, permissions)
   [cache hit]  → Result Validation → Answer Generation → response
   [cache miss] → continue
Query Pipeline → Deterministic Router: can this be answered without an LLM?
   [yes] → Deterministic Planner → IR
   [no]  → Schema Retrieval → Disambiguation check
              [ambiguous] → response: clarification options (no LLM call, or one lightweight call)
              [clear]     → LLM Provider Abstraction (purpose=query_planning) → IR
Query Pipeline → Query Validation (syntax/schema/type/relationship/security)
   [invalid] → LLM Repair (≤2 attempts) → re-validate
Query Pipeline → Complexity Guard → classify LOW/MED/HIGH → apply limits
Query Pipeline → Execution Layer (BackendCompiler for target engine)
   [error] → Repair loop (bounded) or surface failure with transparency
Query Pipeline → Result Validation → Answer Generation (deterministic or LLM)
Query Pipeline → Visualization selection
Query Pipeline → Cache write
Query Pipeline → Audit/Trace/Usage logs
API Gateway → User: answer + table + chart + generated SQL (transparency)
```

---

## 5. Data Architecture

### 5.1 Metadata Database (Supabase / PostgreSQL)
Tables (see SRS/PRD §Entities): `users, workspace_members, workspaces, entitlements, data_sources, files, datasets, tables, columns, relationships, metrics, query_history, query_results, llm_usage, audit_log`. Row-level security policies (using `auth.uid()`, Supabase's convention) scope every table by `workspace_id`.

### 5.2 File Storage (Supabase Storage)
Raw uploaded files, versioned by content hash, stored in a Supabase Storage bucket with Storage-level RLS policies mirroring the table-level workspace-isolation pattern. Lifecycle policies enforce retention per workspace configuration.

### 5.3 Analytical Storage
DuckDB operates directly over files (or a materialized local copy) — no separate analytical warehouse required at MVP scale.

### 5.4 Cache Store (Redis)
Query-plan cache, result cache, and rate-limit counters.

---

## 6. Security Architecture

* **AuthN/AuthZ:** Supabase Auth (email/password, OIDC/SAML); this backend verifies Supabase-issued JWTs rather than issuing its own; RBAC (owner/editor/analyst/viewer) enforced at API and data layer via Supabase RLS (`auth.uid()`-based policies).
* **Workspace isolation:** every query to the metadata DB and every cache key is scoped by `workspace_id`; enforced independent of application-layer bugs via RLS.
* **Credential handling:** external DB credentials stored encrypted (Supabase Vault, or an external KMS if preferred), used only to establish read-only connections.
* **Prompt injection defense:** structural — data values are only ever placed in clearly delimited data blocks in prompts, never in the instruction portion; LLM output is only ever consumed as schema-validated structured IR, never executed as a command.
* **Query safety:** IR compiler and validator allow only `SELECT`/`WITH`-equivalent read operations; sandboxed execution for any Pandas/Python path.
* **PII handling:** catalog-level PII tagging drives masking in results/answers by role; retention/deletion policies enforce guaranteed data removal.
* **Adversarial testing:** part of CI — injection payloads, write-attempt payloads, cross-workspace access attempts, PII-leakage checks (see Development Plan §Testing Strategy).

---

## 7. Scalability & Deployment

* **Containerized services** (API, Query Pipeline, Ingestion, Workers) deployed independently, horizontally scalable behind a load balancer.
* **Stateless API/pipeline layers**; all persistent state in Supabase (Postgres + Storage) and Redis.
* **Async workers** absorb ingestion and schema-refresh load without impacting query latency.
* **Sandboxed Pandas execution** runs in isolated, resource-capped containers/processes, separately scalable from the main query path.
* Environments: dev → staging → production, with the evaluation/regression and adversarial suites gating promotion to production.

---

## 8. Technology Stack Summary

```text
Frontend:             React / Next.js
Backend:              Python, FastAPI
Auth:                 Supabase Auth (email/password, OIDC/SAML); backend
                       verifies Supabase-issued JWTs, does not issue sessions
Analytical engine:    DuckDB
Data processing:      Pandas (sandboxed)
Metadata DB:          Supabase (PostgreSQL + row-level security, + pgvector later)
Cache/rate limiting:  Redis
File storage:         Supabase Storage
Job queue:            Standard async task queue (e.g. Celery/RQ or equivalent)
LLM:                  Provider-neutral abstraction layer; no direct vendor SDK
                       usage outside the adapter modules
```

---

## 9. Key Architectural Decisions (ADR-style summary)

| Decision | Rationale |
|---|---|
| LLM output is always structured IR, never directly executed | Enables validation, backend independence, and safety |
| Single LLM provider interface for all calls | Enables provider swap/failover without touching business logic |
| DuckDB as default file-query engine | Fast, embeddable, no separate warehouse needed at MVP scale |
| Row-level security for workspace isolation | Defense in depth beyond application-layer checks |
| Deterministic-first routing | Reduces cost/latency and reduces LLM dependency surface |
| Versioned Query IR with raw-SQL escape hatch | Lets the IR evolve without breaking cached plans; avoids blocking on IR coverage gaps |
| Sandboxed Pandas execution | Contains risk of any arbitrary-code path |
