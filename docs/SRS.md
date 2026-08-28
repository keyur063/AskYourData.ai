# Software Requirements Specification (SRS)
## AskYourData.ai

**Version:** 1.0
**Conforms to intent of IEEE 830 structure (adapted)**

---

## 1. Introduction

### 1.1 Purpose
Specifies functional and non-functional requirements for AskYourData.ai, derived from the PRD, to guide design, implementation, and testing.

### 1.2 Scope
Covers the web application, backend services, LLM provider abstraction, execution engines (DuckDB, external SQL databases), and supporting infrastructure (auth, rate limiting, caching, observability).

### 1.3 Definitions
* **IR** — Intermediate Representation of a query, produced by the query planner.
* **Workspace** — isolated tenant boundary containing data sources, users, and history.
* **DataSource** — an uploaded file or a connected database.

---

## 2. Overall Description

### 2.1 Product Perspective
A multi-tenant SaaS web application with a Python/FastAPI backend, React/Next.js frontend, DuckDB as the default analytical engine, PostgreSQL as the metadata store, Redis for caching/rate-limiting, and an abstracted LLM provider layer.

### 2.2 User Classes
`owner`, `editor`, `analyst`, `viewer` (see PRD §5, §Roles below).

### 2.3 Operating Environment
Cloud-hosted (containerized services), accessed via modern web browsers; no client install required.

### 2.4 Design & Implementation Constraints
* No write operations against connected external databases, ever.
* All LLM interactions go through a single internal provider-abstraction interface (FR-LLM-*).
* All data access is scoped by `workspace_id` at the data layer, not only in application code.

---

## 3. Functional Requirements

### 3.1 Authentication & Authorization

```
FR-AUTH-1  System shall support email/password and SSO (OIDC/SAML) authentication.
FR-AUTH-2  System shall issue short-lived session tokens with refresh capability.
FR-AUTH-3  System shall support four workspace roles: owner, editor, analyst, viewer.
FR-AUTH-4  System shall enforce role permissions at the API layer AND at the data layer (row-level security or equivalent).
FR-AUTH-5  System shall prevent any cross-workspace data access regardless of role.
FR-AUTH-6  Viewer role shall not be able to run ad-hoc natural-language queries, only view saved results (configurable).
```

### 3.2 Workspace Management

```
FR-WS-1  System shall allow creation of workspaces, each with a unique ID.
FR-WS-2  Workspace owners shall be able to invite/remove members and assign roles.
FR-WS-3  Each workspace shall have an entitlement record (plan tier, limits, feature flags).
FR-WS-4  Deleting a workspace shall delete or anonymize all associated data within a defined retention window (see FR-GOV-*).
```

### 3.3 Data Ingestion

```
FR-ING-1  System shall accept CSV and Excel (.xlsx) file uploads.
FR-ING-2  System shall support multi-sheet Excel files, registering each sheet as a distinct logical table.
FR-ING-3  System shall validate file type, size, row count, and sheet count against configurable limits before processing.
FR-ING-4  System shall detect and reject/quarantine corrupted or malformed files with a clear error.
FR-ING-5  System shall handle merged cells, multi-row headers, and hidden sheets without silent data loss.
FR-ING-6  System shall compute a content hash (e.g. SHA-256) per dataset for versioning.
FR-ING-7  System shall process small files synchronously and large files asynchronously via a job queue, without blocking the API.
FR-ING-8  System shall track file lifecycle state: UPLOADING, PROCESSING, READY, FAILED, DELETING.
```

### 3.4 Data Catalog

```
FR-CAT-1  System shall infer and store schema (column name, type, nullability) per table.
FR-CAT-2  System shall compute column statistics: unique count, null %, sample values, min/max.
FR-CAT-3  System shall infer semantic types (identifier, currency, date, datetime, percentage, category, location, email, name, numeric, text, boolean).
FR-CAT-4  System shall scan columns for PII and tag them with pii_flag/pii_category.
FR-CAT-5  System shall detect candidate relationships (foreign keys) between tables with a confidence score.
FR-CAT-6  System shall store metadata separately from underlying data.
```

### 3.5 Database Connections

```
FR-DB-1  System shall support connecting PostgreSQL, MySQL, and SQL Server data sources.
FR-DB-2  System shall require and enforce read-only credentials for all external connections.
FR-DB-3  System shall encrypt stored connection credentials at rest.
FR-DB-4  System shall auto-catalog schema for connected databases, refreshable on demand or on schedule.
FR-DB-5  System shall detect schema drift on connected databases and invalidate affected caches.
```

### 3.6 Natural Language Query Pipeline

```
FR-NLQ-1  System shall accept a natural-language question scoped to a workspace and (optionally) a conversation thread.
FR-NLQ-2  System shall validate the request and apply rate limiting before further processing.
FR-NLQ-3  System shall check the query-plan/result cache before invoking any LLM.
FR-NLQ-4  System shall route deterministic questions (row count, column list, preview rows, dataset size) to a non-LLM deterministic path.
FR-NLQ-5  System shall retrieve only relevant schema (tables/columns/relationships) for the LLM, not the full workspace schema.
FR-NLQ-6  System shall score planner confidence and trigger a clarification flow when confidence is below threshold or the question is ambiguous.
FR-NLQ-7  System shall maintain conversation context so follow-up questions can modify a prior query plan.
FR-NLQ-8  System shall produce a versioned, structured Query IR as the planner's output.
FR-NLQ-9  System shall support a flagged raw_sql IR variant for cases the structured IR cannot express, subject to stricter validation.
```

### 3.7 Query Validation & Execution

```
FR-VAL-1  System shall validate generated queries for syntax, schema existence, type compatibility, join validity, and permitted operations before execution.
FR-VAL-2  System shall reject any query containing DROP, DELETE, UPDATE, INSERT, ALTER, TRUNCATE, or equivalent write/DDL operations.
FR-VAL-3  System shall estimate query complexity (LOW/MEDIUM/HIGH) and enforce timeout, join, and result-size limits accordingly.
FR-EXE-1  System shall execute validated queries against DuckDB for file-based sources.
FR-EXE-2  System shall execute validated queries against the native engine for connected databases.
FR-EXE-3  System shall support a Pandas execution path compiled from the same Query IR.
FR-EXE-4  System shall run any arbitrary generated Python/Pandas code (if used) in a sandboxed environment with CPU, memory, timeout, import, filesystem, and network restrictions.
FR-EXE-5  On execution error, system shall attempt LLM-based query repair up to a configurable maximum (default 2) before surfacing a failure to the user.
```

### 3.8 Result Handling

```
FR-RES-1  System shall validate results against the requested dimensions/metrics/filters/output shape before presenting an answer.
FR-RES-2  System shall generate answers deterministically for simple results and via LLM only for complex explanations.
FR-RES-3  System shall select an appropriate visualization type (line/bar/pie/scatter/histogram) primarily from the structured result and IR.
FR-RES-4  System shall mask or exclude PII-flagged fields from results/answers per role and workspace configuration.
```

### 3.9 LLM Provider Abstraction

```
FR-LLM-1  All LLM calls shall go through a single internal provider interface accepting (purpose, structured_input, output_schema).
FR-LLM-2  System shall validate every LLM response against a versioned schema before use; invalid responses shall trigger repair or failure, never silent pass-through.
FR-LLM-3  System shall support configuring/switching the underlying LLM provider without changes to downstream components (IR, validation, execution).
FR-LLM-4  System shall support a non-LLM deterministic fallback path for the query types defined in FR-NLQ-4.
FR-LLM-5  System shall log every LLM call: request_id, user_id, workspace_id, provider, model, purpose, tokens, latency, estimated cost.
```

### 3.10 Rate Limiting & Entitlements

```
FR-RATE-1 System shall enforce per-user, per-workspace, and per-IP rate limits across API requests, data queries, LLM calls, expensive queries, and uploads.
FR-RATE-2 Rate limits shall be derived from the workspace's entitlement/plan record and be configurable without code changes.
```

### 3.11 Caching

```
FR-CACHE-1 System shall cache query plans and results keyed by workspace_id, dataset_version, normalized_question, and user permissions.
FR-CACHE-2 Cache entries for connected (live) databases shall expire via TTL and be invalidated on detected schema drift.
FR-CACHE-3 System shall never return a cached result to a user lacking permission for the underlying data.
```

### 3.12 Observability, Audit, and Governance

```
FR-OBS-1  System shall assign a unique request_id to every query and trace it through all pipeline stages.
FR-OBS-2  System shall log cache hit/miss, execution time, and errors per request.
FR-AUDIT-1 System shall maintain an audit log (distinct from LLM usage log) of authentication, connection, upload, query, and membership/role-change events, including who performed them and when.
FR-GOV-1  System shall support a configurable data retention policy per workspace, including guaranteed deletion of files, derived data, and cache entries after workspace/file deletion.
FR-GOV-2  System shall support configuring data residency for storage and metadata where required.
```

### 3.13 Evaluation

```
FR-EVAL-1 System shall support running a benchmark suite of questions with expected schema selection, IR, SQL, execution result, and answer, for regression testing.
FR-EVAL-2 System shall support running an adversarial test suite covering prompt injection, write-operation attempts, cross-workspace access attempts, and PII leakage.
```

---

## 4. Non-Functional Requirements

```
NFR-PERF-1   Median end-to-end query latency (deterministic path) < 2s; (LLM path) < 8s at MVP scale.
NFR-PERF-2   System shall not block API threads during large-file ingestion (async processing).
NFR-SCALE-1  Architecture shall support horizontal scaling of API and worker layers independently.
NFR-SEC-1    All data in transit shall be encrypted (TLS); all credentials and PII at rest shall be encrypted.
NFR-SEC-2    Workspace isolation shall be enforced at the data layer, not solely in application logic.
NFR-SEC-3    No user-supplied data content shall ever be interpreted as an executable instruction (prompt injection or otherwise).
NFR-REL-1    Query repair attempts shall be capped to bound worst-case latency/cost.
NFR-REL-2    Core deterministic query paths (row count, preview, column list) shall remain available even if the LLM provider is unavailable.
NFR-COST-1   System shall track and expose LLM cost per workspace/user/purpose.
NFR-PORT-1   LLM provider and execution backend shall each be swappable behind their respective abstraction without changes to the natural-language pipeline logic.
NFR-USAB-1   Every answer shall be traceable to its generated query (SQL/IR) for user transparency.
NFR-COMPAT-1 Frontend shall support current major versions of Chrome, Firefox, Safari, Edge.
```

---

## 5. External Interface Requirements

* **User interface:** Web app (React/Next.js), responsive, chat-style query interface plus schema explorer and result views.
* **APIs:** REST/JSON API for frontend-backend communication; internal LLM Provider interface (see Architecture doc); internal DataSource interface for file/DB access.
* **Database interfaces:** Native drivers for PostgreSQL, MySQL, SQL Server, invoked only with read-only credentials.

---

## 6. Traceability (excerpt)

| PRD Feature | SRS Requirements |
|---|---|
| F1 Ingestion | FR-ING-1..8 |
| F2 Data Catalog | FR-CAT-1..6 |
| F3/F4 NL Query + Disambiguation | FR-NLQ-1..9 |
| F5 IR + Execution | FR-VAL-*, FR-EXE-* |
| F8 Workspaces/Roles | FR-AUTH-*, FR-WS-* |
| F9 Rate limiting | FR-RATE-* |
| F10 LLM abstraction | FR-LLM-* |
| F15 Caching | FR-CACHE-* |
| F16 Audit | FR-AUDIT-1 |
| F17 PII | FR-CAT-4, FR-RES-4, FR-GOV-* |
