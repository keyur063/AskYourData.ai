# AskYourData.ai — Project Description (v2)

## 1. Project Overview

**AskYourData.ai** is an AI-powered data analytics platform that allows users to upload structured data files such as CSV and Excel files, connect external SQL databases, and query their data using natural language.

The core idea is:

> **Users should be able to ask questions about their data in natural language without manually writing SQL or Python.**

Example:

> "What were the top 10 products by revenue in 2025?"

The system should understand the user's intent, identify the relevant datasets, tables, columns, and relationships, generate a structured query plan, translate that plan into an appropriate execution language such as SQL or Pandas, execute it safely, validate the result, and return a human-readable answer along with optional tables and visualizations.

The platform should be designed from the beginning to support multiple data sources, multiple execution engines, and multiple LLM providers.

---

## 2. Core Design Principles

The architecture should **not** be built around direct:

```text
Natural Language → LLM → SQL
```

Instead, use:

```text
Natural Language
        ↓
Query Understanding / Disambiguation
        ↓
Schema / Metadata Retrieval
        ↓
Query Plan / Intermediate Representation (IR)
        ↓
Validation
        ↓
Execution Backend
        ↓
Result Validation
        ↓
Answer / Visualization
```

Two components are deliberately **replaceable, provider-agnostic abstractions**, not the foundation of the system:

1. **The LLM.** It is a query-planning and language-generation component, invoked through a provider-neutral interface. No part of the system should assume a specific model, prompt format, or vendor API shape. Every LLM-touching stage must define its input/output contract independently of which model fulfills it, and — wherever feasible — have a deterministic fallback that requires no LLM call at all.
2. **The execution engine.** SQL, Pandas, DuckDB, PostgreSQL, MySQL, Polars, Spark, etc. are all just compilation targets for the Query IR.

This abstraction allows AskYourData.ai to swap LLM providers or execution engines without redesigning the natural-language layer, and to keep functioning (in a reduced, deterministic mode) if an LLM provider is unavailable.

---

## 3. Supported Data Sources

### File sources
* CSV
* Excel `.xlsx` (including multi-sheet workbooks)
* eventually Parquet

### Database sources
* PostgreSQL
* MySQL
* SQL Server
* other SQL-compatible databases in the future

All sources are accessed through a common abstraction called a **DataSource**:

```text
DataSource
├── FileDataSource
│   ├── CSV
│   ├── Excel
│   └── Parquet
│
└── SQLDataSource
    ├── PostgreSQL
    ├── MySQL
    └── SQL Server
```

---

## 4. Workspace, Identity & Access Control

Each user belongs to one or more **workspaces**. A workspace contains uploaded files, database connections, logical tables, schemas, metadata, relationships, saved queries, query history, and billing/entitlement state.

Every data operation must be associated with a `workspace_id` **and** an authenticated `user_id`. Workspace isolation is a critical security requirement — users must never access another workspace's files, schemas, metadata, connections, or results.

### Authentication
* Standard email/password and SSO (OIDC/SAML) support, abstracted behind an auth provider interface (same "swap the vendor without redesigning the system" principle applied to auth).
* Session/token-based API auth (JWT or equivalent), short-lived tokens with refresh.

### Authorization (roles, per workspace)

```text
owner   — manage members, billing, connections, delete workspace
editor  — upload data, create connections, edit metadata/semantic layer
analyst — run queries, save queries, view results
viewer  — read-only access to saved queries/dashboards, no ad-hoc querying
```

* Role checks are enforced at the API layer **and** mirrored as row-level security (or equivalent) at the data-catalog and query-execution layer, so a bug in application logic cannot leak cross-workspace or cross-role data.
* Database connection credentials are always scoped to the minimum role needed (read-only) and encrypted at rest, independent of the workspace-role model above.

---

## 5. File Ingestion

```text
Upload
  ↓
File Validation
  ↓
File Storage
  ↓
Parsing
  ↓
Sheet/Table Discovery
  ↓
Schema Inference
  ↓
Statistics Generation
  ↓
Relationship Detection
  ↓
PII / Sensitive-Data Scan
  ↓
Metadata Registration
  ↓
Dataset Ready
```

For an Excel file containing multiple sheets, each sheet becomes a logical table (e.g. `company.xlsx` → `company_employees`, `company_departments`, `company_salaries`, or equivalent workspace-scoped names). The original filename and sheet name are retained as metadata.

Ingestion must explicitly handle common real-world breakage points:
* merged cells
* multi-row or offset headers
* hidden or empty sheets
* inconsistent column types within a column
* duplicate uploads (by content hash)
* files exceeding maximum size, row count, or sheet count

---

## 6. Data Catalog

Maintains metadata about workspaces, data sources, files, tables, columns, relationships, and dataset versions — stored separately from the actual data.

Example table metadata:

```text
Table: orders
Description: Customer order transactions
Columns: order_id, customer_id, product_id, quantity, unit_price, order_date, region
```

Column metadata, where possible:

```text
name, data type, nullable, unique count, null percentage,
sample values, minimum, maximum, semantic type, description,
pii_flag, pii_category
```

Semantic types include: `identifier, currency, date, datetime, percentage, category, location, email, name, numeric, text, boolean`.

The `pii_flag`/`pii_category` fields (populated by the PII scan in §5) drive masking and access-control decisions described in §34.

---

## 7. Dataset Versioning

Every dataset has a version identifier derived from a content hash (e.g. SHA-256):

```text
dataset_id = sales
dataset_version = abc123...
```

Required for reliable caching — queries against version 1 must never accidentally return cached results from version 2.

---

## 8. Relationship Detection

Detected using column name similarity, data type compatibility, uniqueness, value overlap, and primary/foreign-key heuristics. Each relationship carries a confidence score:

```text
source: orders.customer_id
target: customers.customer_id
confidence: 0.97
```

Detection logic should be rule-based/statistical by default, with an optional LLM-assisted pass for ambiguous cases only — never LLM-only.

---

## 9. Schema Retrieval

The full schema is never sent to the LLM for every query. A retrieval step narrows to relevant tables, columns, and relationships first, using metadata filtering and (later) vector/semantic retrieval — improving accuracy, latency, token usage, cost, and scalability.

```text
User Question → Schema Retrieval → Relevant Tables/Columns/Relationships → Query Planner
```

---

## 10. Semantic Layer

Business concepts are defined explicitly rather than inferred by the LLM each time:

```text
Metric: Revenue
Definition: SUM(quantity * unit_price)
```

Other examples: Profit, Gross Margin, Active Customers, Average Order Value, Retention Rate.
Dimensions: Region, Product, Customer, Department, Month, Year.

The semantic layer is available to the query planner as structured, deterministic input — reducing what the LLM has to infer.

---

## 11. Natural Language Query Pipeline

```text
User Question
      ↓
Request Validation & Auth Check
      ↓
Rate Limiter
      ↓
Cache Lookup
      ↓
Intent / Query Router  (LLM needed? see §14)
      ↓
Schema Retrieval
      ↓
Query Understanding & Disambiguation
      ↓
Query Planner
      ↓
Query IR
      ↓
Query Validation
      ↓
Execution
      ↓
Result Validation
      ↓
Answer Generation
      ↓
Visualization
```

---

## 12. Query Understanding & Disambiguation

Ambiguity is resolved explicitly rather than silently guessed. Sources of ambiguity include: multiple candidate columns for a term (e.g. two `date` columns), an undefined metric ("top customers" by revenue vs. by order count), or a filter value that doesn't exist in the data.

```text
Query Planner
      ↓
Confidence Scoring
      ↓
confidence ≥ threshold?  → proceed to Query IR
confidence < threshold?  → emit "needs_clarification" IR
      ↓
Present options to user (deterministic UI, not free-text LLM chat)
      ↓
User selection re-enters the pipeline as pipeline context
```

The clarification options themselves are generated from catalog metadata (candidate columns, known metric definitions) wherever possible, rather than requiring an LLM call to phrase them.

---

## 13. Rate Limiting, Billing & Entitlements

Rate limiting must be implemented from the beginning across multiple dimensions: user, workspace, IP, LLM calls, expensive queries, file uploads.

```text
Free plan:  10 analytical queries/minute,  100 queries/day
Pro plan:   60 analytical queries/minute, 5000 queries/day
```

Limits are configurable and tied to a workspace's **entitlement** record (plan tier, seat count, feature flags), which is the single source of truth both the rate limiter and the UI read from. Redis is recommended for distributed rate limiting. The limiter distinguishes normal API requests, data queries, LLM calls, expensive queries, and uploads.

---

## 14. LLM Call Optimization ("deterministic-first")

Not every query requires an LLM. Deterministic queries (row counts, column listings, `SELECT * LIMIT 10`, dataset size) are answered directly from metadata or generated SQL templates with **no LLM call**.

```text
Can this request be answered without an LLM?
   yes → execute deterministically
   no  → send to LLM query planner (via the LLM Provider Abstraction Layer, §15)
```

This is both a cost optimization and part of the LLM-independence principle: the more of the system that works without a model call, the less the product depends on any single provider's availability, pricing, or behavior.

---

## 15. LLM Provider Abstraction Layer

All LLM usage in the system goes through a single internal interface, not direct vendor SDK calls scattered across the codebase:

```text
LLMProvider (interface)
  .generate(purpose, structured_input, output_schema) → structured_output
```

* `purpose` is one of: `query_planning`, `query_repair`, `disambiguation_phrasing`, `answer_generation`, `visualization_selection`.
* `output_schema` is a strict, versioned JSON schema per purpose — the caller never parses free-text; every response is validated against the schema before use, regardless of which model produced it.
* Prompts/templates per purpose are stored and versioned independently of any single provider's prompt idioms, so switching providers means swapping an adapter, not rewriting business logic.
* The abstraction supports multiple concurrent providers (e.g. for cost/quality routing, or failover if a provider is degraded) and a **local/offline mode** (rule-based query planning for simple, deterministic cases per §14) that requires no LLM at all.
* No component downstream of this layer (Query IR, Validation, Execution) has any awareness of which model or vendor produced the plan — it only consumes the validated structured output.

---

## 16. Query Caching

### Query-plan cache
`question → query plan / SQL`

### Result cache
`query → result`

Cache keys incorporate `workspace_id`, `dataset_version`, `normalized_question`, and `user permissions`, preventing stale or unauthorized results.

For **file-based sources**, `dataset_version` (content hash, §7) makes invalidation exact. For **connected live databases**, there is no content hash to key on, so:
* cached plans/results carry a short TTL (configurable per connection),
* a lightweight schema-diff check (table/column existence, type) runs before reusing a cached plan against a live DB, and
* any detected schema drift invalidates the affected cache entries immediately.

Question normalization initially includes lowercasing and whitespace normalization; semantic similarity caching can be introduced later.

---

## 17. Query IR / Query Plan

The LLM produces a structured, **versioned** intermediate representation rather than directly producing executable SQL or Python.

```json
{
  "ir_version": "1.2",
  "source": "orders",
  "operation": "aggregation",
  "metrics": [{ "column": "revenue", "aggregation": "SUM" }],
  "group_by": ["region"],
  "filters": [{ "column": "year", "operator": "=", "value": 2025 }],
  "order_by": [{ "column": "revenue", "direction": "DESC" }],
  "limit": 10
}
```

`ir_version` allows the IR schema to evolve without breaking cached plans or compiled backends. When a request needs something the structured IR cannot express (correlated subqueries, complex window functions), the planner may emit a `raw_sql` IR variant instead — this path is explicitly flagged, subject to stricter validation and sandboxing than structured IR, and logged separately so its usage can be tracked and minimized over time.

The IR is the contract between the (replaceable) LLM and the (replaceable) execution backend — neither side needs to know about the other.

---

## 18. Execution Backends

Initial backends: **SQL** and **Pandas**. Recommended initial analytical engine: **DuckDB**, serving as the primary execution engine for uploaded CSV/Excel/Parquet data. Pandas remains available as an alternative. Future backends: PostgreSQL, MySQL, Polars, Spark.

## 19. SQL Execution

```text
CSV / Excel / Parquet → DuckDB → SQL
PostgreSQL / MySQL / SQL Server → Native SQL execution
```

The same Query IR should be compilable to both.

## 20. Pandas Execution

```text
Natural Language → Query IR → Pandas Compiler → Pandas execution
```

If arbitrary Python/Pandas code is ever generated directly, it must run in an isolated sandbox with CPU limits, memory limits, execution timeout, restricted imports, restricted filesystem access, and no unrestricted network access.

---

## 21. Query Validation

Generated queries are never blindly executed. Validation covers:
* **Syntax** — does the query parse?
* **Schema** — do tables/columns exist?
* **Type** — are operations compatible with column types?
* **Relationship** — are joins valid?
* **Security** — only permitted operations?

For database connections, generated queries are restricted to read-only operations (`SELECT`, `WITH`) — never `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`.

---

## 22. Prompt Injection & Data Isolation Design

Because sample values and cell contents from user-uploaded data are surfaced to the LLM as context (§6), they are the primary injection surface and must be handled explicitly, not just declared as a requirement:

* Data values (sample values, cell contents, column names from source files) are **never** interpolated into the instruction/system portion of a prompt. They are only ever placed inside clearly delimited, labeled data blocks that the prompt template explicitly frames as *data to reason about*, not *instructions to follow*.
* The LLM's output is only ever consumed as structured IR validated against a schema (§15, §17) — it is never re-executed as a command, never used to alter system prompts, and never used to bypass the role/permission checks from §4.
* Any text resembling an instruction found inside dataset values (e.g. a cell containing "ignore previous instructions") is treated purely as data content to be queried, and never actioned.
* This is tested continuously via the adversarial suite described in §37.

---

## 23. Query Repair

```text
Generated Query → Validation → Execution → Error → LLM Repair → Validation → Execution
```

Retries are capped (`MAX_QUERY_REPAIR_ATTEMPTS = 2`) to prevent runaway cost. If repair still fails after the cap, the user sees the last attempted query and a plain-language explanation of what failed, plus an option to rephrase — never a silent dead end.

---

## 24. Query Complexity Guard

Before execution, estimate complexity from number of tables/joins, aggregation, sorting, window functions, and estimated rows/result size. Classify `LOW / MEDIUM / HIGH` and enforce query timeout, max joins, max result size, max rows scanned, memory limits, and expensive-query rate limits accordingly.

---

## 25. LLM Usage Tracking

Every LLM call (through the abstraction layer in §15) is logged: `request_id, user_id, workspace_id, provider, model, purpose, input tokens, output tokens, total tokens, latency, estimated cost, timestamp`. Because all calls flow through one interface, cost/latency comparisons across providers and models are a query over this log, not a code change.

---

## 26. Request Tracing

Every query receives a unique `request_id`, with all pipeline events (API request, rate-limit check, cache lookup, schema retrieval, LLM call, generated IR, generated SQL, execution, result, final answer) associated with it for debugging and observability.

---

## 27. Audit Logging

Distinct from LLM usage tracking (§25): a durable, workspace-scoped audit log of **who did what to which data**, independent of whether an LLM was involved:

```text
timestamp, user_id, workspace_id, action, resource_type, resource_id, role_at_time, ip
```

Actions include login, connection created/deleted, file uploaded/deleted, query executed, result viewed, member added/removed, role changed. Required for enterprise customers and for investigating any suspected cross-workspace access issue.

---

## 28. Conversation Context

Follow-up questions maintain and modify the previous QueryPlan/context rather than treating every question as independent:

```text
"What are the top 5 products by revenue?"
"Only for Maharashtra."
"Compare those with last year."
```

---

## 29. Result Validation

Successful execution does not mean the answer is correct. Results are checked against requested dimensions, metrics, filters, expected output shape, and aggregation semantics — e.g. "highest-paid employee" should return a name and amount, not a bare number.

---

## 30. Answer Generation

```text
Simple results:  SQL → Result → Deterministic formatter   (no LLM)
Complex results: Result → LLM → Natural language explanation
```

---

## 31. Visualization

Visualization type is inferred primarily from the structured result and QueryPlan (time series → line, categories → bar, part-to-whole → pie/donut, two numeric variables → scatter, distribution → histogram) — a deterministic mapping, not an LLM decision, except for edge cases.

---

## 32. File Lifecycle

```text
UPLOADING → PROCESSING → READY → FAILED → DELETING
```

Ingestion handles invalid/corrupted files, unsupported formats, duplicates, and size/row/sheet limits.

---

## 33. Async Processing

```text
Upload → API → Job Queue → Worker → Parse/Analyze/Index → READY
```

Small files can be processed synchronously initially; the architecture supports worker-based processing for larger datasets from the start.

---

## 34. Data Governance & PII

* The PII scan from §5 flags columns as `pii_flag`/`pii_category` (email, name, phone, government ID, etc.) in the Data Catalog.
* PII-flagged columns can be masked or excluded from LLM-visible sample values and from answer text by default, configurable per workspace/role (a `viewer` may see aggregates but not raw PII, for example).
* Explicit, configurable **retention policy**: how long uploaded files and derived data persist, and guaranteed deletion (including from caches and backups within a stated window) when a workspace or file is deleted.
* Data residency should be a configurable property of file storage and the metadata database, anticipating regulated customers (EU, etc.) even if not required at MVP.

---

## 35. Security

* Auth & role-based access control (§4)
* Workspace isolation, enforced at the data layer
* Read-only, encrypted database credentials
* Strict SQL validation, read-only operations only
* Sandboxed Pandas/Python execution
* File type, size, and content validation
* Query timeouts and resource limits
* Explicit prompt-injection design (§22), not just a stated goal
* Data values are always treated as data, never as instructions
* PII masking and retention controls (§34)
* Audit logging (§27)

---

## 36. Observability

Log and monitor: request ID, user, workspace, question, selected tables/columns, generated QueryPlan/IR, generated SQL, execution time, cache hit/miss, LLM provider/latency/token usage/cost, query success/failure, errors. Internal monitoring dashboards are a near-term goal, not an eventual one.

---

## 37. Evaluation Framework

### Correctness suite
A benchmark of representative questions with expected schema selection, IR, SQL, execution result, and final answer — every major prompt/model/architecture change is tested against this regression suite, including when swapping LLM providers (this is what actually proves LLM-independence: the same suite should pass, within tolerance, against more than one provider).

### Safety / adversarial suite
Run continuously, not just at launch:
* Prompt-injection payloads embedded in cell values, column names, and filenames
* Attempts to elicit write operations (`DROP`, `DELETE`, etc.) through the NL layer
* Cross-workspace boundary tests (attempting to reference another workspace's tables/IDs)
* PII leakage tests (does a query result surface masked fields it shouldn't)
* Query-complexity/DoS attempts (deliberately expensive queries)

---

## 38. Suggested Initial Technology Stack

```text
Frontend:            React / Next.js
Backend:              Python, FastAPI
Auth:                 OIDC-compatible provider behind an internal auth interface
Analytical engine:    DuckDB
Data processing:      Pandas
Metadata database:    PostgreSQL (with row-level security for workspace isolation)
Cache / rate limiting:Redis
File storage:         S3-compatible object storage
Vector search:        optional initially; pgvector inside PostgreSQL later
LLM:                  Provider-neutral abstraction layer (§15); no hard dependency
                       on a single vendor SDK anywhere else in the codebase
```

---

## 39. Initial Database Entities

```text
users
roles / workspace_members
workspaces
entitlements
data_sources
files
datasets
tables
columns
relationships
metrics
query_history
query_results
llm_usage
audit_log
```

All relevant entities are associated with `workspace_id`; `workspace_members` links `users` to `workspaces` with a role.

---

## 40. Recommended MVP

### MVP data sources
CSV, Excel

### MVP execution
DuckDB

### MVP query flow
```text
Auth & role check
 ↓
Upload
 ↓
Schema discovery + PII scan
 ↓
Data Catalog
 ↓
Natural language question
 ↓
Rate limit
 ↓
Cache
 ↓
Relevant schema retrieval
 ↓
Disambiguation (if needed)
 ↓
LLM (via provider abstraction)
 ↓
Query IR (versioned)
 ↓
SQL
 ↓
Validation
 ↓
DuckDB
 ↓
Result
 ↓
Answer
```

### MVP UI
Upload dataset → Dataset preview → Schema/table explorer → Chat interface (with clarification prompts when needed) → Generated SQL → Result table → Basic charts → Query history

The MVP intentionally includes auth/roles and the LLM provider abstraction from day one — both are far more expensive to retrofit than to build in from the start, even at small scale.

---

## 41. Future Roadmap

```text
Phase 1: CSV + Excel + DuckDB + NL querying + auth/roles + LLM abstraction layer
Phase 2: Multiple files/sheets + joins + schema retrieval + disambiguation
Phase 3: Query IR versioning + raw-SQL fallback + SQL/Pandas execution abstraction
Phase 4: PostgreSQL/MySQL/SQL Server connections + live-DB cache invalidation + PII/governance
Phase 5: Semantic layer + business metrics
Phase 6: Conversational analytics
Phase 7: Charts + dashboards + saved queries + audit log UI
Phase 8: Advanced analytics, anomaly detection, forecasting, automated insights
```

---

## 42. Final Architectural Principle

AskYourData.ai should be designed as a **data query platform with an AI interface**, not simply as an LLM application — and specifically not as an application built around any single LLM vendor.

```text
Data Source
     ↓
Data Catalog (with governance/PII awareness)
     ↓
Schema / Semantic Layer
     ↓
Natural Language → Disambiguation
     ↓
Query Plan / IR (versioned, provider-agnostic)
     ↓
Execution Backend
     ↓
Validation
     ↓
Result
     ↓
Answer / Visualization
```

The system must prioritize:

1. **Correctness**
2. **Security** (including auth/authz, prompt-injection design, and PII governance)
3. **Cost efficiency**
4. **Scalability**
5. **Observability**
6. **Backend and LLM-provider independence**
7. **Good user experience**

Both the LLM and the execution engine are replaceable components behind stable, versioned interfaces — never the foundation the rest of the system is built on top of.
