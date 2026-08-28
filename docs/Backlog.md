# Implementation Backlog
## AskYourData.ai — agent-actionable tickets

Each ticket has a scope small enough for a single agent session, references the
governing SRS requirement(s), and states its acceptance check. Tickets are
grouped by Development Plan phase; within a phase, do them roughly top to
bottom (later tickets depend on earlier ones unless noted).

---

## Phase 0 — Foundations

**T0.1 — Repo scaffold**
Create the directory structure in `repo-scaffold.md` with empty/stub files and working `docker-compose.yml`.
*Accept:* `docker compose up` brings up postgres, redis, backend (health check 200), frontend (loads blank page).

**T0.2 — DB baseline migration (Supabase)**
Apply `db/schema.sql` to your Supabase project via `supabase db push` (or the SQL editor), including the `auth.users` sync trigger, `is_workspace_member`/`has_workspace_role` functions, and all RLS policies. Set up Alembic for *future* migrations only (baseline is `db/schema.sql` itself, not Alembic-generated).
*Accept:* schema applies cleanly to a fresh Supabase project; a query as user A (via their JWT/anon key + RLS) can never see user B's workspace rows — test this in the Supabase SQL editor with `set role authenticated; set request.jwt.claims...` or via two real signed-up test users hitting the API.
*Refs:* NFR-SEC-2

**T0.3 — Auth: wire up Supabase Auth (email/password + SSO)**
No custom JWT issuance. Frontend uses `@supabase/supabase-js` (or equivalent) to sign up/log in directly against Supabase Auth (email/password, and OIDC/SAML providers configured in the Supabase dashboard). Backend implements `core/security.py` to verify the Supabase-issued JWT on incoming requests (Supabase's public JWKS) and extract `user_id`.
*Accept:* a user signed up via Supabase Auth can call a protected backend endpoint with their Supabase access token and it resolves to the correct `user_id`; an expired/invalid token is rejected with 401; confirm the `on_auth_user_created` trigger populates `public.users` correctly.
*Refs:* FR-AUTH-1, FR-AUTH-2
*Note: this replaces the original T0.3/T0.4 pair (custom JWT + OIDC callback) — Supabase Auth covers both in one ticket.*

**T0.4 — Role-gated write policies**
The RLS policies in `db/schema.sql` currently gate SELECT via `is_workspace_member`. Add explicit `for insert`/`for update`/`for delete` policies per workspace-scoped table using `has_workspace_role(workspace_id, 'editor')` etc., matching the role matrix in SRS FR-AUTH-3 (owner/editor/analyst/viewer permissions).
*Accept:* an `analyst`-role user's attempt to `INSERT` into `files` (bypassing the API, direct DB test) is rejected by RLS, not just by application logic; an `owner` can manage members, an `editor` cannot.
*Refs:* FR-AUTH-3, FR-AUTH-4

**T0.5 — Workspace + role middleware**
Implement `require_role(min_role)` FastAPI dependency: resolves the caller's role for the target `workspace_id` (query `workspace_members`, itself RLS-protected) and rejects with 403 before the handler runs. Because RLS uses `auth.uid()` automatically from the passed-through JWT, there is no manual session-context-setting step — just ensure the backend's DB connection for a given request authenticates as that user (not the service-role key) wherever RLS should apply.
*Accept:* a request scoped to workspace A with a token for workspace B returns 403 before touching workspace A's data; confirm via test that using the *service-role* key anywhere in the normal request path is impossible (lint/code-review check, not just a runtime test) except in explicitly designated trusted worker paths (e.g. retention worker).
*Refs:* FR-AUTH-3, FR-AUTH-4, FR-AUTH-5

**T0.6 — Workspace + member endpoints**
Implement `/workspaces` (GET/POST), `/workspaces/{id}/members` (GET/POST), `/workspaces/{id}/members/{user_id}` (PATCH/DELETE) exactly per `api/openapi.yaml`.
*Accept:* contract tests generated from the OpenAPI spec pass; only `owner` can invite/remove/change roles.
*Refs:* FR-WS-1, FR-WS-2

**T0.7 — Entitlements record + rate limiter skeleton**
Create entitlement row on workspace creation (default `free` plan values from `db/schema.sql` defaults). Implement Redis-backed rate limiter middleware reading limits from the entitlement record.
*Accept:* exceeding `queries_per_minute` returns 429 with `RateLimited` schema (limit, reset_at).
*Refs:* FR-WS-3, FR-RATE-1, FR-RATE-2

**T0.8 — LLM Provider Abstraction skeleton**
Implement `LLMProvider` ABC (`generate(purpose, input, schema) -> output`), one adapter (Anthropic), and a schema-validation wrapper that rejects any adapter output failing its JSON Schema.
*Accept:* a stub call with `purpose="query_planning"` round-trips through the adapter, validates against a placeholder schema, and is written to `llm_usage`.
*Refs:* FR-LLM-1, FR-LLM-2, FR-LLM-5

**T0.9 — Request tracing**
Assign `request_id` per inbound request, propagate through logs, persist in `query_history`/`llm_usage` where applicable.
*Accept:* a single `request_id` can be grepped across API, pipeline, and LLM usage logs for one query.
*Refs:* FR-OBS-1

---

## Phase 1 — MVP: CSV/Excel + DuckDB + NL Querying

**T1.1 — File upload endpoint + validation**
Implement `POST /workspaces/{id}/files` (multipart), enforcing size/row/sheet limits from the entitlement record, storing the raw file in Supabase Storage (path convention: `{workspace_id}/{content_hash}/{filename}`, with a Storage RLS policy mirroring `is_workspace_member`), creating a `files` row in `UPLOADING` state.
*Accept:* oversized file rejected with clear error before storage write; valid file transitions to `PROCESSING`; a user from workspace B cannot read/download workspace A's file object directly from Storage (test the Storage policy, not just the API route).
*Refs:* FR-ING-1, FR-ING-3

**T1.2 — CSV/Excel parser**
Implement parsing for CSV and multi-sheet Excel, handling merged cells, multi-row/offset headers, hidden sheets, per Ingestion §5 edge cases.
*Accept:* a fixture set of "messy" Excel files (merged headers, hidden sheet, blank leading rows) all parse into correct logical tables without silent data loss — write these fixtures first.
*Refs:* FR-ING-2, FR-ING-5

**T1.3 — Schema inference + stats**
Infer column types, nullability, unique count, null %, sample values, min/max; write to `catalog_columns`.
*Accept:* known fixture dataset produces expected stats within tolerance.
*Refs:* FR-CAT-1, FR-CAT-2

**T1.4 — Semantic type inference**
Classify each column into the semantic_type enum using heuristics (regex for email, name patterns, currency symbols, date parsing, etc.).
*Accept:* fixture dataset's semantic types match an expected-output fixture file.
*Refs:* FR-CAT-3

**T1.5 — PII scan**
Flag `pii_flag`/`pii_category` per column using semantic type + pattern detection (email, phone, national ID patterns).
*Accept:* fixture dataset with known PII columns is correctly flagged; a clean numeric dataset has zero false positives.
*Refs:* FR-CAT-4, FR-ING-5 (governance dependency, Phase 4 enforcement)

**T1.6 — Async ingestion worker**
Move parsing/inference/PII-scan out of the request path into `ingestion_worker.py` via job queue for files above a size threshold; keep small files synchronous.
*Accept:* uploading a large fixture file returns 202 immediately; state transitions UPLOADING→PROCESSING→READY are observable via polling `GET /files/{id}`.
*Refs:* FR-ING-7, FR-ING-8

**T1.7 — Data Catalog read endpoints**
Implement `GET /catalog/tables`, `GET /catalog/tables/{id}` per OpenAPI.
*Accept:* contract tests pass; PII-flagged columns show `pii_flag=true` in response.
*Refs:* FR-CAT-*

**T1.8 — Query IR validator**
Implement `ir/validator.py` using `schemas/query-ir.schema.json` (jsonschema library). Reject anything not matching a known `ir_version`.
*Accept:* valid structured/needs_clarification/raw_sql fixtures pass; malformed IR (wrong enum value, missing required field) is rejected with a specific error.
*Refs:* FR-NLQ-8, FR-VAL-1

**T1.9 — DuckDB BackendCompiler**
Implement `execution/duckdb_backend.py` compiling a validated structured `QueryIR` into DuckDB SQL and executing against the relevant file-backed table(s).
*Accept:* a set of IR fixtures (aggregation, filter, group_by, order_by, limit) each produce correct results against a known fixture dataset.
*Refs:* FR-EXE-1

**T1.10 — Query safety validator**
Implement the syntax/schema/type/relationship/security validation pipeline; explicitly reject write/DDL keywords even inside `raw_sql` IR.
*Accept:* adversarial fixture set (attempted DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE via both structured filter-value injection and raw_sql) is 100% rejected pre-execution.
*Refs:* FR-VAL-1, FR-VAL-2, NFR-SEC-3

**T1.11 — Deterministic router + planner**
Implement pattern-matching for row-count/column-list/preview/dataset-size questions; route these to `deterministic_planner.py`, bypassing the LLM entirely.
*Accept:* fixture questions of these types never generate an `llm_usage` row.
*Refs:* FR-NLQ-4, FR-LLM-4

**T1.12 — Schema retrieval (filtering-based)**
Implement relevant-table/column selection given a question and full catalog, using metadata filtering (keyword/column-name matching) as the v1 approach.
*Accept:* fixture questions against a multi-table workspace retrieve only the expected subset of tables/columns (measured, not just spot-checked).
*Refs:* FR-NLQ-5

**T1.13 — LLM query planner (prompt + schema)**
Author `prompts/query_planning_v1.yaml` and its output JSON Schema; wire through the Provider Abstraction (T0.8) to produce structured `QueryIR`.
*Accept:* fixture question set (≥30 questions spanning aggregation/filter/group_by types) produces IR matching expected-IR fixtures on ≥90%.
*Refs:* FR-NLQ-6 (confidence), FR-NLQ-8, FR-LLM-1..3

**T1.14 — Confidence scoring + clarification IR**
Add confidence output to the planner schema; below threshold, planner emits `needs_clarification` IR instead of guessing.
*Accept:* deliberately ambiguous fixture questions (two candidate date columns, undefined "top" metric) produce `needs_clarification`, not a silent guess.
*Refs:* FR-NLQ-6

**T1.15 — Clarification resume endpoint**
Implement `POST /query/{request_id}/clarify`, merging the selected option's `resolves_to` patch into `candidate_partial_ir` and re-entering the pipeline at validation.
*Accept:* end-to-end: ambiguous question → clarification options → selection → correct final answer, without re-running the full planner.
*Refs:* FR-NLQ-6

**T1.16 — Query repair loop**
On execution error, retry via LLM repair (`prompts/query_repair_v1.yaml`) up to `MAX_QUERY_REPAIR_ATTEMPTS`; surface last attempt + error on exhaustion.
*Accept:* fixture set of deliberately broken IR (bad column name) is repaired within the cap; a fixture designed to be unrepairable exhausts the cap and returns a structured error, not a hang or crash.
*Refs:* FR-EXE-5, NFR-REL-1

**T1.17 — Complexity guard**
Classify LOW/MEDIUM/HIGH from IR (table count, joins, aggregation, estimated rows) and enforce timeout/result-size limits before execution.
*Accept:* a fixture query designed to scan an oversized result set is capped/rejected before completing, within a bounded time.
*Refs:* FR-VAL-3

**T1.18 — Result validation**
Check result shape against requested dimensions/metrics (e.g. a "who is X" question must return a name column, not just a bare aggregate).
*Accept:* fixture question "highest-paid employee" returns name+amount, not amount alone; a mismatch fixture is caught and flagged rather than silently returned.
*Refs:* FR-RES-1

**T1.19 — Answer generation (deterministic + LLM)**
Simple results → deterministic formatter (no LLM). Complex results → `answer_generation_v1.yaml` prompt.
*Accept:* simple-result fixtures never trigger an LLM call; complex-result fixtures produce a grammatical, correct-per-data answer.
*Refs:* FR-RES-2

**T1.20 — Visualization selector**
Deterministic mapping from IR shape → chart type per Architecture §deterministic mapping.
*Accept:* fixture IRs of each shape (time series, categorical, two-numeric, distribution) map to the expected chart type with no LLM call.
*Refs:* FR-RES-3

**T1.21 — Query/result caching**
Implement cache key construction and lookup/write around the pipeline per FR-CACHE-1.
*Accept:* identical question + same dataset_version + same permissions returns cached result with `cache_hit=true` and no new LLM call; a permission-different user never receives another user's cached result even for an identical question string.
*Refs:* FR-CACHE-1, FR-CACHE-3

**T1.22 — `POST /query` endpoint (full wiring)**
Wire T1.1–T1.21 into `query_pipeline/orchestrator.py` behind the `POST /workspaces/{id}/query` endpoint per OpenAPI.
*Accept:* full contract test suite against `api/openapi.yaml` passes for this endpoint across all `QueryResponse.status` variants.
*Refs:* FR-NLQ-1..3

**T1.23 — Query history endpoints**
Implement `GET /query/history` with filters; persist every request to `query_history`.
*Accept:* filters (dataset_id, user_id, date range) return correct subsets against fixture data.
*Refs:* (supports PRD F7)

**T1.24 — Evaluation benchmark v1**
Build `tests/evaluation/` with ≥30 fixture questions covering P0 types, expected schema selection, IR, SQL, result, and answer; wire into CI.
*Accept:* CI fails if benchmark accuracy drops below the committed threshold (start at 90% on P0 types).
*Refs:* FR-EVAL-1

**T1.25 — Adversarial suite v1**
Build `tests/adversarial/` covering: prompt injection via cell values/filenames, write-operation attempts (structured and raw_sql), cross-workspace access attempts, rate-limit bypass attempts.
*Accept:* CI fails on any single adversarial fixture succeeding; wire as a release-blocking gate.
*Refs:* FR-EVAL-2, NFR-SEC-3

**T1.26 — Frontend: upload + preview + chat MVP**
Build upload flow, dataset preview, and chat interface (question → answer card w/ table + chart + "View SQL" + clarification card) per UI/UX §2.1–2.3, §3.1.
*Accept:* manual E2E: upload fixture CSV → ask 5 scripted questions (incl. one ambiguous) → correct answers/clarifications render per design.

---

## Phase 2 — Multi-file / Joins / Context

**T2.1 — Relationship detection**
Implement `relationship_detection.py` (name similarity, type compatibility, value overlap) writing to `relationships` with confidence scores.
*Refs:* FR-CAT-5

**T2.2 — Join support in IR + DuckDB compiler**
Extend planner prompt + compiler to emit/consume the `joins` array in Query IR.
*Refs:* FR-NLQ-8 (extended), FR-EXE-1

**T2.3 — Conversation context**
Persist `query_threads`; modify planner input to include prior turn's IR for follow-up questions ("only for Maharashtra").
*Refs:* FR-NLQ-7

**T2.4 — Improved schema retrieval**
Move beyond keyword filtering (e.g. embeddings-based ranking) while keeping the interface unchanged for the planner.
*Refs:* FR-NLQ-5

---

## Phase 3 — IR Versioning & Execution Abstraction

**T3.1 — IR version migration strategy**
Define and implement handling for cached plans/results referencing an older `ir_version` when the schema evolves.
*Refs:* FR-NLQ-8

**T3.2 — raw_sql path hardening**
Implement the stricter validator for `kind=raw_sql` (single statement, SELECT/WITH only, declared `source_tables` cross-checked against actual referenced tables).
*Refs:* FR-NLQ-9, FR-VAL-2

**T3.3 — Pandas backend (sandboxed)**
Implement `pandas_backend/compiler.py` + `sandbox_runner.py` (separate process/container, CPU/memory/timeout/import/network restrictions).
*Refs:* FR-EXE-3, FR-EXE-4

---

## Phase 4 — External DB Connections & Governance

**T4.1 — DB connection CRUD + credential encryption**
Implement `/data-sources` endpoints, KMS-backed encryption of credentials, enforced read-only role check on connect.
*Refs:* FR-DB-1, FR-DB-2, FR-DB-3

**T4.2 — Connection test endpoint**
Implement `/data-sources/{id}/test`, verifying connectivity and read-only enforcement explicitly (attempt a harmless write and confirm rejection, or verify grants).
*Refs:* FR-DB-2

**T4.3 — External schema auto-cataloging**
Extend catalog service to introspect connected DB schemas into `catalog_tables`/`catalog_columns`.
*Refs:* FR-DB-4

**T4.4 — Schema drift detection + cache invalidation**
Implement `schema_refresh_worker.py`: periodic diff against last-cataloged schema; invalidate affected cache entries on drift.
*Refs:* FR-DB-5, FR-CACHE-2

**T4.5 — SQL backend (native execution)**
Implement `execution/sql_backend.py` for Postgres/MySQL/SQLServer, compiling the same Query IR.
*Refs:* FR-EXE-2

**T4.6 — PII masking enforcement**
Implement `governance/pii_masking.py`, applied in result/answer generation based on `pii_flag` + caller role.
*Refs:* FR-RES-4

**T4.7 — Retention policy + deletion workflow**
Implement configurable retention windows and guaranteed deletion (files, derived data, cache) on workspace/file deletion.
*Refs:* FR-GOV-1

**T4.8 — Audit log**
Implement `audit/logger.py` hooks on auth, connection, upload, query, and membership/role-change events; implement `GET /audit-log`.
*Refs:* FR-AUDIT-1

---

## Phase 5 — Semantic Layer

**T5.1 — Metrics CRUD**
Implement `/metrics` endpoints and `semantic_layer.py` resolution logic (planner references `semantic_metric_refs`, compiler resolves to the stored definition).
*Refs:* PRD F13

---

## Phase 6 — Conversational Depth + Provider Independence Proof

**T6.1 — Second LLM provider adapter**
Implement `adapters/openai_adapter.py` implementing the same `LLMProvider` interface.
*Refs:* FR-LLM-3

**T6.2 — Cross-provider benchmark run**
Run the Phase 1 evaluation benchmark (T1.24) against both providers; document accuracy/cost/latency delta.
*Accept:* both providers pass the same accuracy threshold without any pipeline code change — this is the concrete proof of NFR-PORT-1.

---

## Phase 7 — Dashboards & Saved Queries

**T7.1 — Saved queries**
Persist and list user-saved queries per workspace; surface in query history UI.

**T7.2 — Usage dashboard**
Implement `GET /usage` and a frontend usage view per UI/UX §3.5.
*Refs:* FR-LLM-5, NFR-COST-1

---

## Cross-cutting (apply throughout, not a phase)

* Every new endpoint must have a contract test generated/checked against `api/openapi.yaml` before merge.
* Every new IR-touching change must run the evaluation benchmark before merge.
* Every new execution-path change must run the adversarial suite before merge.
* No PR may introduce a direct LLM vendor SDK import outside `backend/app/llm/adapters/` (lint-enforced).
