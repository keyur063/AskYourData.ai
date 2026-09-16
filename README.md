# AskYourData.ai

Upload a CSV, ask questions about it in plain English, get back a validated
answer with the SQL that produced it. Built as a lean, safety-first MVP —
natural language is never trusted directly against your data; every
question is compiled into a structured, validated query before anything
executes.

## What this actually does

1. Upload a CSV — schema (columns, types) is inferred automatically.
2. Ask a question in plain English (e.g. "how many students enrolled in
   2025?").
3. A Groq-hosted LLM (your own API key, not a shared platform key) plans
   the query as a structured intermediate representation — never raw SQL
   generated blindly.
4. That plan is validated: schema-checked, and explicitly blocked if it
   contains any write/delete/update/drop-style intent — read-only, always.
5. The validated plan compiles to SQL and runs against your data via DuckDB.
6. You get a plain-language answer, a result table, and the exact SQL that
   ran — full transparency, nothing hidden.

Every user brings their own Groq API key (encrypted at rest, never
returned by the API once saved). Multi-tenant workspace isolation is
enforced by PostgreSQL Row-Level Security at the database layer, not just
application code.

## Tech stack

- **Backend:** Python / FastAPI
- **Frontend:** Next.js (App Router) / TypeScript
- **Database & Auth:** Supabase (PostgreSQL + Row-Level Security + Auth)
- **Query execution:** DuckDB
- **LLM:** Groq (OpenAI-compatible API), per-user key, encrypted with Fernet

## Project structure

```text
backend/app/
├── api/                    # FastAPI routes
│   ├── workspaces.py       # workspace CRUD
│   ├── files.py            # CSV upload
│   ├── catalog.py          # schema/table inspection
│   ├── query.py            # natural language query endpoint
│   └── me.py                # per-user Groq API key management
├── core/
│   ├── config.py            # env-driven settings
│   ├── security.py          # Supabase JWT verification
│   └── supabase_client.py   # Supabase client wrapper
├── ingestion/                # CSV parsing, validation, schema inference
├── catalog/                  # schema/table metadata service
├── ir/
│   └── validator.py          # validates the LLM's query plan against a schema
├── execution/
│   ├── duckdb_backend.py     # compiles the validated plan to SQL, runs it
│   └── safety_validator.py   # rejects any write/DDL intent — the core
│                              #   safety boundary of the whole system
├── llm/
│   ├── provider_interface.py # abstract LLM provider contract
│   ├── adapters/groq_adapter.py
│   ├── key_store.py           # per-user encrypted API key storage
│   ├── planner.py             # turns a question into a structured plan
│   ├── confidence.py          # low-confidence fallback (asks to rephrase
│   │                          #   instead of guessing)
│   └── repair.py               # retries a failed query once with the error
│                                #   fed back to the LLM
└── query_pipeline/
    └── orchestrator.py         # wires the whole flow above together

frontend/app/
├── login/page.tsx
├── dashboard/page.tsx         # workspace list
├── workspace/[id]/page.tsx    # upload, schema preview, chat interface
├── settings/page.tsx          # Groq API key management
└── lib/
    ├── supabase-client.ts
    └── api-client.ts
```

## Running it locally

### 1. Prerequisites
- Python 3.11+
- Node.js
- A Supabase project (free tier is fine) with the schema in
  `db/schema-lean.sql` applied
- A Groq API key from [console.groq.com](https://console.groq.com) — each
  user of the app provides their own; you'll need one for your own testing

### 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:
```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
GROQ_BASE_URL=https://api.groq.com/openai/v1
ENCRYPTION_KEY=
MAX_QUERY_REPAIR_ATTEMPTS=1
MAX_FILE_SIZE_MB=5
MAX_ROWS_SCANNED=1000000
QUERY_TIMEOUT_SECONDS=10
```

Generate `ENCRYPTION_KEY` once (used to encrypt every user's stored Groq
key — back it up somewhere safe, losing it makes stored keys
unrecoverable):
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Run it:
```bash
uvicorn app.main:app --reload
```

Check it's alive: `curl http://localhost:8000/health`

### 3. Frontend setup

```bash
cd frontend
npm install
```

Copy `.env.local.example` to `.env.local` and fill in:
```text
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run it:
```bash
npm run dev
```

Visit `http://localhost:3000`.

### 4. First use

1. Sign up / log in.
2. Go to **Settings**, add your Groq API key.
3. Create a workspace, upload a CSV.
4. Ask a question about it in the chat interface.

## Security properties (verified, not just claimed)

These were tested directly against a running instance, not assumed from
code review alone:

- **No write operations ever execute** — delete/update/drop/insert/alter
  intent is explicitly detected and blocked before the query planner even
  runs.
- **Prompt injection via data is inert** — cell values from uploaded CSVs
  are never interpolated into the LLM's instructions; only column
  names/types are. A cell containing text like "ignore previous
  instructions" is returned as plain data, never followed.
- **Cross-workspace access is blocked at the database layer** — enforced
  by PostgreSQL RLS, confirmed by replaying a real request from one user's
  session against another user's workspace ID and getting a 404, not data.
- **API keys are encrypted at rest** and never returned by any endpoint
  once saved.
