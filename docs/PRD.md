# Product Requirements Document (PRD)
## AskYourData.ai

**Version:** 1.0
**Status:** Draft

---

## 1. Purpose

Define what AskYourData.ai must do for its users, why, and how success will be measured. This document is the source of truth for scope decisions; the SRS derives detailed functional/non-functional requirements from it, and the System Architecture document derives the technical design.

---

## 2. Problem Statement

Business users, analysts, and operators routinely need answers from structured data (spreadsheets, exported reports, operational databases) but:

* Writing SQL or Pandas requires technical skill most stakeholders don't have.
* Data analysts become a bottleneck for routine, repetitive questions.
* Existing BI tools require pre-built dashboards; they don't answer novel, ad-hoc questions well.
* Off-the-shelf "chat with your data" tools often send raw data or full schemas to an LLM with weak validation, creating correctness and security risk.

**Opportunity:** a product that lets anyone ask data questions in plain language, gets a validated, correct answer, and does so safely — without being locked to one LLM vendor or one data engine.

---

## 3. Vision

> Any authorized user can ask a question about their organization's data in plain language and get a correct, explainable, safely-generated answer — regardless of which LLM or database is powering it underneath.

---

## 4. Goals

| Goal | Description |
|---|---|
| G1 | Let non-technical users query CSV/Excel data and connected SQL databases in natural language |
| G2 | Guarantee generated queries are safe (read-only, validated, sandboxed) before execution |
| G3 | Keep the system correct — validated results, not just "successfully executed" queries |
| G4 | Keep the system cost-efficient — minimize unnecessary LLM calls |
| G5 | Keep the system provider-independent — swappable LLM and execution backends |
| G6 | Provide workspace-level collaboration with proper access control |
| G7 | Provide enough observability/audit trail for enterprise adoption |

### Non-Goals (for initial scope)
* Building a general-purpose BI/dashboarding replacement
* Writing back to source data (no INSERT/UPDATE/DELETE from the product)
* Real-time streaming data sources
* On-premise/self-hosted deployment (cloud SaaS only, initially)

---

## 5. Target Users / Personas

**Priya — Business Analyst (primary)**
Comfortable with Excel, not with SQL. Wants fast answers to "what changed" and "who/what is top/bottom" questions without waiting on the data team.

**Raj — Data/Analytics Engineer (secondary, admin)**
Sets up database connections, defines the semantic layer (metrics/dimensions), manages workspace membership and permissions, monitors query/LLM cost.

**Meera — Executive / Occasional User**
Asks infrequent, high-level questions ("how did Q3 revenue compare to Q2"), needs answers in plain language plus a chart, not raw SQL.

**Compliance/IT Stakeholder (non-active user, has requirements)**
Cares about data residency, PII handling, audit trails, and access control — a blocker persona whose requirements must be satisfied for enterprise sales even though they may never open the product themselves.

---

## 6. Key User Stories

```
US-1  As Priya, I can upload a CSV/Excel file and immediately ask questions about it.
US-2  As Priya, I can ask a follow-up question ("only for Maharashtra") without restating context.
US-3  As Priya, if my question is ambiguous, I'm asked to clarify rather than given a silently wrong answer.
US-4  As Meera, I get a plain-language answer plus a relevant chart, not just a data table.
US-5  As Raj, I can connect a read-only PostgreSQL/MySQL database and have its schema auto-cataloged.
US-6  As Raj, I can define business metrics (e.g. "Revenue") once and have them reused across queries.
US-7  As Raj, I can see LLM cost and query volume per workspace/user.
US-8  As a workspace owner, I can invite members and assign roles (owner/editor/analyst/viewer).
US-9  As a workspace owner, I can be confident my data is never visible to another workspace.
US-10 As Compliance, I can see an audit log of who accessed or queried what data, and configure retention.
US-11 As Raj, if the query fails, I see what was attempted and why, with a chance to rephrase.
US-12 As a platform operator, I can change the underlying LLM provider without users noticing a behavior change.
```

---

## 7. Feature Requirements Overview

| # | Feature | Priority |
|---|---|---|
| F1 | File upload & ingestion (CSV, Excel, multi-sheet) | P0 |
| F2 | Data Catalog (schema, stats, semantic types, PII flags) | P0 |
| F3 | Natural language query with chat interface | P0 |
| F4 | Query disambiguation / clarification flow | P0 |
| F5 | Query IR generation + validated SQL execution (DuckDB) | P0 |
| F6 | Result table + basic auto-charting | P0 |
| F7 | Query history | P0 |
| F8 | Workspaces, roles, invitations | P0 |
| F9 | Rate limiting & entitlements (plan tiers) | P0 |
| F10 | LLM provider abstraction (multi-provider capable) | P0 |
| F11 | Conversation context / follow-up questions | P1 |
| F12 | External DB connections (Postgres/MySQL/SQL Server) | P1 |
| F13 | Semantic layer (metrics & dimensions) | P1 |
| F14 | Relationship detection across tables | P1 |
| F15 | Query/result caching | P1 |
| F16 | Audit log (distinct from LLM usage log) | P1 |
| F17 | PII detection & masking | P1 |
| F18 | Saved queries / dashboards | P2 |
| F19 | Anomaly detection / forecasting | P3 |

---

## 8. Success Metrics

**Adoption**
* % of new workspaces with ≥1 successful query within first session
* Weekly active querying users per workspace

**Quality**
* Query success rate (executes without error) — target ≥95%
* Answer correctness rate on the evaluation benchmark (§ Evaluation Framework, SRS) — target ≥90% on P0 question types
* Clarification rate (how often disambiguation triggers) tracked as a leading indicator, not purely minimized — a spurious wrong answer is worse than an occasional clarifying question

**Cost & Performance**
* Median query latency (question → answer)
* LLM cost per successful query
* % of queries answered without any LLM call (deterministic path)

**Trust/Safety**
* Zero cross-workspace data exposure incidents
* Zero successful prompt-injection-driven policy violations in the adversarial test suite
* 100% of write-operation attempts blocked pre-execution

---

## 9. Assumptions & Constraints

* Initial release is cloud SaaS, multi-tenant, with strict workspace isolation.
* Initial file size/row limits will be conservative and raised as async processing matures.
* The product must remain functional (in a reduced, deterministic mode) if the primary LLM provider is degraded or unavailable.
* No source data is ever modified — the product is read-only against connected databases.

---

## 10. Risks

| Risk | Mitigation |
|---|---|
| LLM produces plausible-but-wrong queries | Query IR validation, result validation, evaluation benchmark, human-readable query transparency |
| Prompt injection via uploaded data | Explicit data/instruction separation, adversarial test suite (see System Architecture §Security) |
| Cost overrun from unnecessary LLM calls | Deterministic-first routing, caching, usage tracking/alerts |
| Vendor lock-in to one LLM provider | Provider abstraction layer, benchmark run against multiple providers |
| Cross-workspace data leakage | Row-level security, per-request workspace scoping, audit log |
| Users misunderstand a correct-but-incomplete answer | Result validation against expected output shape, explicit "assumptions made" note in answers |

---

## 11. Release Plan Summary

See **Development Plan** document for phased delivery. MVP = F1–F10 (P0 features) on CSV/Excel + DuckDB only.
