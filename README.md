# AskYourData.ai

This repo contains the full spec for AskYourData.ai. **If you're working under
a limited/constrained agent-session budget, start with the Lean MVP path
below — it's the recommended default.** The full spec remains the reference
for scaling back up later.

## Lean MVP (recommended starting point)

1. `docs/Lean-MVP-Scope.md` — what's in/out of scope for the reduced build, and why
2. `docs/Lean-Backlog.md` — session-sized tickets (7 sessions, commit after each)
3. `db/schema-lean.sql` — the 8-table schema this scope uses

Everything else below is the full-scope reference — read it for context, but
build against the Lean docs first.

## Full spec (reference / where to scale back up to later)

If you are a coding agent starting work here, read in this order:

1. `docs/PRD.md` — what we're building and why
2. `docs/SRS.md` — functional/non-functional requirements (FR-xxx IDs used everywhere else)
3. `docs/System-Architecture.md` — components, data flow, security architecture
4. `docs/UIUX.md` — screens and interaction patterns
5. `docs/Repo-Scaffold.md` — exact target directory layout and dev environment setup (Supabase-based)
6. `docs/Development-Plan.md` — phases and team/timeline context
7. `docs/Backlog.md` — full-scope, phase-ordered tickets. Each references an SRS requirement ID and states an accept/reject check.

Machine-readable source-of-truth files (referenced throughout the docs above,
do not duplicate or fork these — import/reference them):

- `schemas/query-ir.schema.json` — the Query IR contract (planner ↔ execution)
- `api/openapi.yaml` — the full REST API contract
- `db/schema.sql` — PostgreSQL DDL including row-level security policies

`docs/Project-Description.md` is the original narrative spec these were derived
from — useful for context, superseded by the documents above for anything
where they disagree.

## Where to write code

Generate backend code into `backend/` and frontend code into `frontend/`
following the layout in `docs/Repo-Scaffold.md` exactly — it specifies which
module each responsibility belongs in. Do not invent an alternate structure.

## Hard constraints (see SRS + Architecture for rationale)

- No direct LLM vendor SDK calls outside `backend/app/llm/adapters/`.
- No write-capable SQL (`DROP/DELETE/UPDATE/INSERT/ALTER/TRUNCATE`) anywhere
  in `backend/app/execution/` or produced by `backend/app/ir/`.
- Every workspace-scoped DB table must have an RLS policy — see `db/schema.sql`.
- Every new endpoint needs a contract test against `api/openapi.yaml`.
- Every IR-touching change runs the evaluation benchmark before merge.
- Every execution-path change runs the adversarial suite before merge.
