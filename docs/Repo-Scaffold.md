# Repository Scaffold & Dev Setup
## AskYourData.ai

This defines the target repo layout and local environment so a coding agent
can generate files into the right place instead of inventing a structure.

---

## 1. Repository Layout

```text
askyourdata/
├── backend/
│   ├── app/
│   │   ├── main.py                       # FastAPI app entrypoint
│   │   ├── api/                          # route handlers, one module per resource
│   │   │   ├── auth.py
│   │   │   ├── workspaces.py
│   │   │   ├── members.py
│   │   │   ├── files.py
│   │   │   ├── data_sources.py
│   │   │   ├── catalog.py
│   │   │   ├── metrics.py
│   │   │   ├── query.py
│   │   │   ├── usage.py
│   │   │   └── audit_log.py
│   │   ├── core/
│   │   │   ├── config.py                 # env-driven settings
│   │   │   ├── security.py               # verifies Supabase-issued JWTs, extracts user id/role
│   │   │   ├── supabase_client.py        # Supabase client (service-role, for trusted backend paths)
│   │   │   ├── rate_limiter.py
│   │   │   └── logging.py                # request tracing, request_id propagation
│   │   ├── db/
│   │   │   ├── session.py                # SQLAlchemy engine/session; passes caller's JWT through
│   │   │   │                             # to Postgres (via Supabase connection) so RLS applies
│   │   │   └── models/                   # ORM models mirroring db/schema.sql
│   │   ├── ingestion/
│   │   │   ├── validators.py             # file type/size/row/sheet limits
│   │   │   ├── parsers.py                # CSV/Excel parsing, multi-sheet, merged cells
│   │   │   ├── schema_inference.py
│   │   │   ├── stats.py
│   │   │   ├── pii_scan.py
│   │   │   └── relationship_detection.py
│   │   ├── catalog/
│   │   │   ├── service.py
│   │   │   └── semantic_layer.py
│   │   ├── llm/
│   │   │   ├── provider_interface.py     # LLMProvider ABC — generate(purpose, input, schema)
│   │   │   ├── provider_router.py        # selects active provider per purpose
│   │   │   ├── adapters/
│   │   │   │   ├── anthropic_adapter.py
│   │   │   │   └── openai_adapter.py     # added Phase 6 to validate independence
│   │   │   ├── deterministic_planner.py  # non-LLM path for FR-NLQ-4 query types
│   │   │   ├── prompts/                  # versioned prompt templates per purpose
│   │   │   │   ├── query_planning_v1.yaml
│   │   │   │   ├── query_repair_v1.yaml
│   │   │   │   ├── disambiguation_v1.yaml
│   │   │   │   └── answer_generation_v1.yaml
│   │   │   └── schemas/                  # per-purpose output JSON Schemas
│   │   ├── query_pipeline/
│   │   │   ├── orchestrator.py           # the sequence in Architecture §4
│   │   │   ├── cache.py
│   │   │   ├── disambiguation.py
│   │   │   ├── validator.py              # syntax/schema/type/relationship/security checks
│   │   │   ├── complexity_guard.py
│   │   │   ├── repair.py
│   │   │   ├── result_validator.py
│   │   │   ├── answer_generator.py
│   │   │   └── visualization_selector.py
│   │   ├── ir/
│   │   │   ├── schema/                   # copy of schemas/query-ir.schema.json, versioned
│   │   │   └── validator.py              # jsonschema validation entrypoint
│   │   ├── execution/
│   │   │   ├── backend_interface.py      # BackendCompiler ABC
│   │   │   ├── duckdb_backend.py
│   │   │   ├── sql_backend.py            # Postgres/MySQL/SQLServer, read-only
│   │   │   └── pandas_backend/
│   │   │       ├── compiler.py
│   │   │       └── sandbox_runner.py     # isolated process/container execution
│   │   ├── governance/
│   │   │   ├── retention.py
│   │   │   └── pii_masking.py
│   │   └── audit/
│   │       └── logger.py
│   ├── workers/
│   │   ├── ingestion_worker.py
│   │   ├── schema_refresh_worker.py      # connected-DB schema drift detection
│   │   └── retention_worker.py
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── evaluation/                   # FR-EVAL-1 benchmark suite + fixtures
│   │   └── adversarial/                  # FR-EVAL-2 safety suite + fixtures
│   ├── alembic/                          # DB migrations, generated from db/schema.sql intent
│   ├── pyproject.toml
│   └── Dockerfile
│
├── frontend/
│   ├── app/                              # Next.js app router
│   │   ├── (auth)/
│   │   ├── workspace/[workspaceId]/
│   │   │   ├── chat/
│   │   │   ├── catalog/
│   │   │   ├── data-sources/
│   │   │   ├── history/
│   │   │   ├── settings/members/
│   │   │   ├── settings/usage/
│   │   │   └── settings/audit-log/
│   │   └── layout.tsx
│   ├── components/
│   │   ├── chat/                         # answer cards, clarification cards
│   │   ├── catalog/
│   │   ├── charts/
│   │   └── common/
│   ├── lib/
│   │   ├── api-client.ts                 # generated/typed from api/openapi.yaml
│   │   └── auth.ts
│   ├── package.json
│   └── Dockerfile
│
├── schemas/
│   └── query-ir.schema.json              # source of truth, imported by backend/ir/schema
│
├── api/
│   └── openapi.yaml                      # source of truth, used to generate frontend client
│
├── db/
│   └── schema.sql                        # source of truth for Alembic baseline migration
│
├── infra/
│   ├── docker-compose.yml                # postgres, redis, backend, frontend, worker
│   ├── k8s/ (later)
│   └── ci/
│       └── pipeline.yml                  # runs unit+integration+evaluation+adversarial suites
│
├── docs/
│   ├── PRD.md
│   ├── SRS.md
│   ├── System-Architecture.md
│   ├── UIUX.md
│   └── Development-Plan.md
│
└── README.md
```

---

## 2. Local Dev Environment (Supabase)

Postgres, Auth, and Storage are provided by Supabase rather than self-hosted
containers. Two supported setups:

**Option A — Supabase Cloud (recommended for most dev work)**
Create a free Supabase project, run `db/schema.sql` against it (via the
Supabase SQL editor or `supabase db push`), and point the backend at its
connection string / API URL / keys. No local Postgres container needed.

**Option B — Supabase CLI, fully local**
`supabase start` runs the full stack locally (Postgres, Auth, Storage,
Studio) in Docker, useful for offline dev or CI. Requires the Supabase CLI
installed separately from `docker-compose.yml`.

`infra/docker-compose.yml` now only needs to bring up the app services and
Redis — Postgres/Auth/Storage come from Supabase (cloud or `supabase start`):

```yaml
services:
  redis:
    image: redis:7
    ports: ["6379:6379"]

  backend:
    build: ../backend
    env_file: .env
    depends_on: [redis]
    ports: ["8000:8000"]

  worker:
    build: ../backend
    command: ["python", "-m", "app.workers.run"]
    env_file: .env
    depends_on: [redis]

  frontend:
    build: ../frontend
    env_file: .env
    ports: ["3000:3000"]
    depends_on: [backend]
```

### Required environment variables (`.env`, not committed)

```text
# Supabase project (cloud) or local `supabase start` output
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=<anon key>              # used by frontend for Supabase Auth client
SUPABASE_SERVICE_ROLE_KEY=<service role key>  # backend only, bypasses RLS — never exposed to frontend
DATABASE_URL=postgresql://postgres:<password>@db.<project-ref>.supabase.co:5432/postgres

REDIS_URL=redis://redis:6379/0
LLM_DEFAULT_PROVIDER=anthropic
ANTHROPIC_API_KEY=<key>
OPENAI_API_KEY=<key, added Phase 6>
MAX_QUERY_REPAIR_ATTEMPTS=2
```

Notes:
- `SUPABASE_SERVICE_ROLE_KEY` bypasses RLS entirely — it is used only by
  trusted backend paths that must legitimately cross workspace boundaries
  (e.g. the retention/deletion worker), never for normal request handling.
  Normal API requests should use the caller's own JWT so RLS applies.
- The backend no longer issues its own JWTs (T0.3 is now "wire up Supabase
  Auth client + verify Supabase-issued JWTs", not "build a JWT issuer" —
  see updated Backlog.md).
- File uploads go to Supabase Storage instead of a generic S3-compatible
  endpoint; `OBJECT_STORAGE_*` vars are replaced by the Supabase client
  config above (Storage uses the same project URL/keys).

### Bootstrap sequence for a fresh clone

```bash
cp .env.example .env
# Option A: create project at supabase.com, then:
supabase link --project-ref <project-ref>
supabase db push                      # applies db/schema.sql

# Option B: fully local
supabase start                        # prints local URL/keys — copy into .env

docker compose -f infra/docker-compose.yml up -d redis
docker compose -f infra/docker-compose.yml up -d backend worker frontend
```

---

## 3. Conventions

* **Python:** 3.11+, FastAPI, SQLAlchemy 2.x, Pydantic v2 for all request/response and IR models (generated/kept in sync with `schemas/query-ir.schema.json` and `api/openapi.yaml`).
* **Frontend:** TypeScript, Next.js App Router, API client types generated from `api/openapi.yaml` (do not hand-write duplicate types).
* **Migrations:** Alembic; `db/schema.sql` is the human-readable source of truth reviewed in PRs, migrations are generated from model changes and diffed against it.
* **No direct LLM vendor SDK imports outside `backend/app/llm/adapters/`.** Enforced via a lint rule/CI check — this is what keeps the provider abstraction real rather than aspirational.
* **No write-capable SQL statements anywhere in `execution/` or `ir/` — enforced by the validator, tested by the adversarial suite on every CI run.**
