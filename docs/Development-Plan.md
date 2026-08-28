# Development Plan
## AskYourData.ai

**Version:** 1.0

---

## 1. Delivery Approach

Iterative, phase-based delivery aligned to the roadmap in the project description. Each phase ends with the evaluation benchmark and adversarial safety suite run against it before promotion — these gates are non-negotiable, not optional QA.

---

## 2. Team Structure (suggested, small-team baseline)

```text
1  Tech Lead / Architect        — owns architecture, LLM abstraction, IR design
2  Backend Engineers            — pipeline, execution backends, validation, caching
1  Frontend Engineer            — chat UI, schema explorer, dashboards
1  Data/ML Engineer             — prompt templates, evaluation & adversarial suites, provider adapters
1  DevOps/Platform Engineer     — infra, CI/CD, observability, security hardening (part-time acceptable at MVP)
1  Product/Design               — PRD/UX ownership, user testing
```
Roles can combine for very small teams; the Tech Lead and Data/ML Engineer functions should not be dropped even at minimum scale, since the LLM-abstraction and evaluation suite are what keep the product provider-independent and safe.

---

## 3. Phased Plan

### Phase 0 — Foundations (pre-MVP, ~2–3 weeks)
* Repo setup, CI/CD skeleton, environments (dev/staging/prod)
* Auth provider integration, workspace/role data model, RLS policies in Postgres
* LLM Provider Abstraction Layer skeleton (interface + one adapter + schema validation)
* Basic observability (request tracing, structured logging)

**Exit criteria:** a logged-in user can create a workspace; a stub LLM call round-trips through the abstraction layer and is logged.

### Phase 1 — MVP: CSV/Excel + DuckDB + NL Querying (~5–7 weeks)
* File ingestion pipeline (validation, storage, parsing, schema inference, stats, PII scan)
* Data Catalog (schema/stats/semantic types) + basic schema explorer UI
* NL query pipeline: rate limiting → cache lookup → deterministic router → schema retrieval → LLM planner → Query IR → validation → DuckDB execution → result validation → answer generation → chart selection
* Disambiguation flow (basic, enumerable-option based)
* Query history, basic chat UI
* Evaluation benchmark v1 (P0 question types) + adversarial suite v1 (injection, write-attempt, cross-workspace tests)

**Exit criteria:** PRD success metrics for query success rate and benchmark correctness met on internal test data; adversarial suite passes 100%.

### Phase 2 — Multi-file / Joins / Schema Retrieval Maturity (~3–4 weeks)
* Relationship detection across tables, join support in IR/compiler
* Improved schema retrieval (beyond simple filtering)
* Conversation context / follow-up questions
* Query/result caching with normalization

### Phase 3 — Query IR Versioning & Execution Abstraction (~3–4 weeks)
* Formalize IR versioning, migration strategy for cached plans
* Raw-SQL fallback path with stricter validation/sandboxing
* Pandas execution backend (sandboxed) as an alternate compiler target
* Query repair loop hardening, complexity guard tuning

### Phase 4 — External Database Connections & Governance (~4–6 weeks)
* Postgres/MySQL/SQL Server connectors (read-only enforced)
* Schema auto-cataloging + drift detection + cache invalidation
* PII masking enforcement in results/answers by role
* Retention policy configuration, guaranteed deletion workflows
* Audit log (distinct from LLM usage log) + viewer UI

### Phase 5 — Semantic Layer (~2–3 weeks)
* Metrics/dimensions definition UI and storage
* Planner integration: semantic layer consulted before raw column inference

### Phase 6 — Conversational Analytics Depth (~3 weeks)
* Deeper multi-turn context handling, clarification quality improvements
* Provider abstraction maturity: add a second LLM provider adapter, run benchmark across both to validate independence

### Phase 7 — Dashboards & Saved Queries (~3–4 weeks)
* Saved queries, basic dashboards, sharing within workspace
* Usage/cost dashboards for admins

### Phase 8 — Advanced Analytics (ongoing, post-launch)
* Anomaly detection, forecasting, automated insights

---

## 4. Testing Strategy

| Layer | Approach |
|---|---|
| Unit | Standard unit tests per service (ingestion, catalog, compiler, validator) |
| Integration | Full pipeline tests against representative datasets, including multi-provider LLM runs |
| Evaluation benchmark | Automated regression suite (SRS FR-EVAL-1); run on every prompt/model/architecture change; run against ≥2 providers before any provider-default change ships |
| Adversarial/safety suite | Automated (SRS FR-EVAL-2); run in CI on every merge to main and before every production release; failure blocks release |
| Load/performance | Query latency and concurrency testing before each major phase's release, focused on the deterministic and LLM paths separately |
| Security review | Credential handling, RLS policy review, and PII flow review at end of Phase 4 minimum |

---

## 5. Milestones & Rough Timeline

```text
Week 0–3:   Phase 0 (Foundations)
Week 3–10:  Phase 1 (MVP)               ← first internal/beta release candidate
Week 10–14: Phase 2 (Joins/Context)
Week 14–18: Phase 3 (IR versioning/Pandas)
Week 18–24: Phase 4 (DB connections/Governance)  ← enterprise-readiness milestone
Week 24–27: Phase 5 (Semantic layer)
Week 27–30: Phase 6 (Conversational depth + 2nd LLM provider validated)
Week 30–34: Phase 7 (Dashboards)
Week 34+:   Phase 8 (Advanced analytics, ongoing)
```
Timeline is indicative for a small team (~6–7 people) and should be recalibrated once team size/skill mix is finalized.

---

## 6. Dependencies & Sequencing Notes

* Auth/roles and the LLM abstraction layer are built in Phase 0 deliberately — every later phase depends on both, and retrofitting either later is significantly more expensive than building them first.
* PII tagging (Phase 1, part of ingestion) must exist before Phase 4's masking enforcement — the flag is cheap to add early even if enforcement UI comes later.
* The evaluation benchmark should start small in Phase 1 and grow with every phase; it is the mechanism that proves LLM-independence claims, so it must exist before a second provider is ever evaluated in Phase 6.
* External DB connections (Phase 4) should not start before workspace RLS and audit logging are solid — this is the point at which the product starts touching customer-owned production data.

---

## 7. Definition of Done (per feature)

A feature is done when:
1. It has passing unit + integration tests.
2. It is reflected in the relevant SRS requirement(s) with no open gaps.
3. It passes the evaluation benchmark (if it affects the query pipeline) or the adversarial suite (if it affects security/data boundaries).
4. It has observability (logs/metrics/traces) sufficient to debug it in production without code changes.
5. It has UX copy/states reviewed against the UI/UX document (loading, error, empty, success states all defined).
