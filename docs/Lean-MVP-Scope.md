# Lean MVP Scope
## AskYourData.ai — reduced for limited agent-session budget

**Purpose of this document:** the original PRD/SRS/Backlog describe the full
product. This document defines a genuinely minimal slice that is still a real,
working product — not a toy — sized to be buildable in a handful of focused
Antigravity sessions rather than dozens. Nothing here contradicts the original
docs; it's a subset, and everything cut is explicitly listed so it can be
added back later without rearchitecting.

---

## 1. What stays (the core loop)

The one thing the product must do end-to-end:

```text
Sign up → Upload a CSV → Ask a question in plain English →
Get a validated, correct answer with a chart → See the SQL that produced it
```

Everything in this document is organized around making that loop real,
safe, and demonstrable — not around feature completeness.

---

## 2. Cuts from the original scope

| Area | Full scope | Lean scope | Why cut |
|---|---|---|---|
| Data sources | CSV, Excel (multi-sheet), later DB connections | **CSV only** | Excel parsing edge cases (merged cells, multi-header) are a real chunk of work for no core-loop value yet |
| Auth | Supabase Auth, SSO, 4 roles | **Supabase Auth, email/password only, 2 roles** (owner, member) | SSO and 4-tier RBAC are enterprise features with no bearing on proving the core loop |
| Execution | DuckDB + Pandas (sandboxed) + external SQL | **DuckDB only** | Pandas sandbox is a meaningful isolated-execution project on its own; defer entirely |
| LLM | Provider abstraction + 2 providers + deterministic router | **Provider abstraction (interface only) + 1 provider (Anthropic)** | Keep the *interface* (it's what preserves independence and costs almost nothing extra to define correctly) but skip building/proving a second adapter now |
| Disambiguation | Full confidence-scored clarification flow | **Single fallback: if planner confidence is low, say so and ask the user to rephrase** — no structured clarification UI yet | The clarification UI is real frontend + backend work; a plain-text fallback preserves the safety property (never silently guess) for near-zero cost |
| Caching | Query-plan + result cache, live-DB drift invalidation | **Skip entirely for lean MVP** | Pure cost/latency optimization, not correctness or safety — safe to defer |
| Query repair | LLM repair loop, capped retries | **Keep** (cheap, high value — prevents dead-end failures) | |
| Complexity guard | Full LOW/MED/HIGH classification | **Simple hard caps**: max rows scanned, fixed query timeout | 90% of the safety value for 10% of the work |
| PII/governance | Detection, masking, retention policy, residency | **Skip entirely for lean MVP** | Only matters once real/sensitive data is involved; CSV-upload demo data won't need it yet |
| Audit log | Full action log + viewer UI | **Skip entirely for lean MVP** | Rely on Supabase's own auth logs + query_history table for now |
| Relationships/joins | Cross-table detection, multi-table IR | **Single-table queries only** | Joins are real planner + compiler complexity; defer |
| Semantic layer | Metrics/dimensions editor | **Skip entirely for lean MVP** | |
| Conversation context | Multi-turn follow-ups | **Skip for lean MVP** — every question is independent | Meaningful context-passing work; defer |
| Rate limiting | Redis-backed, multi-dimension | **Simple per-user in-memory or DB counter** | Redis adds an infra dependency for a demo-scale product |
| Async ingestion | Job queue + worker | **Synchronous only**, small file-size cap (e.g. 5MB) | Removes an entire infra component (queue/worker) |
| Evaluation/adversarial suites | Full CI-gated benchmark + adversarial suite | **Keep a small version** (10 questions, 5 adversarial cases) run manually, not CI-gated yet | The *safety validation* (no write SQL, no injection) must not be cut — only the automation/scale of testing it |

---

## 3. What is explicitly NOT cut (non-negotiable even in lean scope)

These are the properties that make this a safe product rather than a toy —
cutting them would change what's actually being built, not just its scope:

* Query IR as the contract between LLM and execution — **no direct NL→SQL**.
* Query validation before execution — read-only enforcement (`SELECT`/`WITH` only, reject all write/DDL keywords).
* LLM output is always schema-validated before use.
* Workspace isolation via Supabase RLS (even with only 2 roles).
* The LLM Provider interface (even with one adapter behind it) — this is what stops you from having to rearchitect later if you switch providers or add Gemini via Vertex.
* Basic request tracing (a `request_id` per query, logged) — costs almost nothing and is what makes debugging possible at all.

---

## 4. Lean Data Model

Trimmed from the full 15-table schema to 8 tables:

```text
users            (Supabase Auth-linked, as before)
workspaces
workspace_members     (role: owner | member — not 4-tier)
files                 (CSV only; skip sheets/multi-table complexity)
catalog_tables
catalog_columns       (skip pii_flag/pii_category columns for now)
query_history         (includes query_ir, generated_sql, status)
llm_usage             (keep — cheap, and directly answers "am I close to quota")
```

Cut for now: `entitlements`, `data_sources`, `datasets` (fold into `files`), `relationships`, `metrics`, `query_threads`, `query_results` (fold into `query_history` as a JSON column), `audit_log`.

---

## 5. Lean API Surface

```text
POST   /auth/*              (Supabase-handled, not custom)
POST   /workspaces
GET    /workspaces
POST   /workspaces/{id}/files
GET    /workspaces/{id}/files/{file_id}
GET    /workspaces/{id}/catalog/tables
GET    /workspaces/{id}/catalog/tables/{table_id}
POST   /workspaces/{id}/query
GET    /workspaces/{id}/query/history
```

Everything else in the full `api/openapi.yaml` (members management beyond invite, data-sources, metrics, usage dashboard, audit-log) is deferred — the file itself doesn't need to change, just build a subset of it.

---

## 6. Lean Query IR

Same `schemas/query-ir.schema.json`, but for lean MVP the planner only ever
emits `kind: "structured"` with no `joins` array populated (single table),
plus a plain-text low-confidence fallback instead of `kind: "needs_clarification"`.
The schema doesn't need to change — you're just not exercising its full
surface yet. This matters: when you *do* add joins/clarification/raw_sql
later, nothing about the contract has to change, only what the planner emits.

---

## 7. Revised Session Plan (see Lean-Backlog.md for exact tickets)

```text
Session 1: Supabase project + lean schema + Supabase Auth wiring
Session 2: File upload (sync, CSV only) + parsing + schema inference
Session 3: Data catalog endpoints + basic frontend (upload + preview)
Session 4: Query IR validator + DuckDB compiler + safety validator
Session 5: LLM planner (single provider) + query pipeline wiring
Session 6: Query repair loop + complexity caps + frontend chat UI
Session 7: Manual eval (10 Qs) + manual adversarial check (5 cases) + fixes
```

Each session is scoped to fit comfortably in one quota window based on the
tickets in Lean-Backlog.md — if a session still runs long, split it further
rather than pushing through into a second quota window mid-task.

---

## 8. Path back to full scope

Nothing here is a dead end. Re-adding a cut feature later:

* **Excel support** → extend the same ingestion module, no architecture change.
* **Second LLM provider** → implement a second adapter behind the existing interface.
* **Joins** → the IR schema already supports `joins`; extend the planner prompt + DuckDB compiler.
* **PII/governance/audit** → additive columns/tables + new middleware; doesn't touch existing tables.
* **Caching, async ingestion, rate limiting via Redis** → additive infra, no rework of existing logic.
* **4-tier roles, SSO** → extend the `workspace_role` enum and RLS policies; existing 2-role logic still works as a subset.

The full `docs/Backlog.md` remains the reference for exactly these next
tickets when you're ready to scale back up.
