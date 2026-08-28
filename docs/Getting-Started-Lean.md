# Getting Started From Scratch
## AskYourData.ai — Lean MVP, Supabase + Groq + FastAPI + Next.js

This assumes nothing exists yet. Ignore any prior scaffold. Read this,
then work `docs/Lean-Backlog.md` ticket by ticket (L1.1 onward).

---

## 1. Stack

```text
Frontend:    Next.js (App Router) + TypeScript + Tailwind
Backend:     Python 3.11+ / FastAPI
Database:    Supabase (Postgres + Auth + Storage)
LLM:         Groq, behind an internal provider interface (single adapter for now)
Local infra: Docker Compose for the backend/frontend containers only
             (no Postgres/Redis containers — Supabase provides Postgres,
             and lean scope skips Redis/caching entirely)
```

Why this combination: Supabase removes three infra components (Postgres,
auth server, file storage) you'd otherwise have to run and secure yourself.
FastAPI + Next.js is a standard, well-documented pairing an agent can
scaffold reliably. Groq as a single provider keeps Session 5 (the LLM
planner) simple — the `LLMProvider` interface still gets built properly so
swapping/adding a provider later is a new adapter file, not a rewrite.

---

## 2. Order of Operations

Do these in order — each step depends on the one before it.

### Step 1 — Supabase project
1. Create a project at supabase.com (or run `supabase start` locally via the CLI if you want a fully offline setup).
2. Note down: Project URL, `anon` public key, `service_role` secret key, and the direct Postgres connection string. **Keep these out of the agent conversation entirely** — put them straight into `.env` files yourself (see §4), never paste them into a prompt.
3. Apply `db/schema-lean.sql` via the Supabase SQL editor (paste and run) or `supabase db push` if using the CLI.
4. In Supabase Dashboard → Authentication, confirm email/password sign-up is enabled (it is by default).
5. In Supabase Dashboard → Storage, create a bucket named `files` (private, not public).

**Verify before moving on:** sign up a test user via the Supabase Auth UI/API directly, confirm a row appears in `public.users` (the trigger should fire automatically), confirm a workspace you insert manually shows up correctly gated by RLS when queried as that user vs. a second test user.

### Step 2 — Groq: platform config only (end-users bring their own key)
Users configure their own Groq API key (per L5.0/L5.0F in the backlog) via the app's Settings page — you as the developer don't need a Groq account to build most of this, and no single platform-wide `GROQ_API_KEY` gets stored in `.env`.

What you *do* need to set up now:
1. `GROQ_BASE_URL` in `backend/.env` — this is the same endpoint for every user (Groq's API URL), platform-wide config, not a secret. Check Groq's current docs for the exact value.
2. `ENCRYPTION_KEY` in `backend/.env` — the symmetric key that encrypts every end-user's stored Groq key. Generate it once (see the `.env.example` snippet in §4) and keep it safe — this is the one secret in this step that genuinely is yours as the operator, not a per-user credential.
3. For your own local testing during development (Sessions 5–7), get a personal Groq API key from console.groq.com and enter it through your own app's Settings page once it exists (L5.0F) — the same way any real user would — rather than putting it in `.env`. This exercises the actual BYOK flow instead of a shortcut.

Groq hosts open-weight models only (Llama, Qwen, GPT-OSS, Kimi K2, etc.) — no GPT/Claude/Gemini-class proprietary models. Users should be able to see/pick a model in Settings (L5.0F); default to one with reliable structured-output/JSON-schema support if they haven't chosen. Groq's free tier requires no credit card but has real rate limits (roughly 30 req/min, 6,000 tokens/min, 14,400 req/day per key at time of writing, confirm current numbers) — since each user has their own key, this is naturally per-user rather than a shared bottleneck across your whole app.

### Step 2.5 — Working without real secrets present
The agent can build and verify almost everything before real credentials
ever exist:
- `.env.example` files (committed, placeholder values only) define every
  variable name the code expects — the agent writes these and reads from
  them via `config.py`, never hardcodes a value.
- `.env` / `.env.local` (actual secrets) go in `.gitignore` from the first
  commit and are edited by you directly, outside the agent's tool access if
  your setup allows scoping that.
- The agent can write and unit-test everything downstream of "a valid
  Supabase/Groq client exists" using mocked clients — Steps 3–5 don't
  require live credentials at all.
- Only the **verification step** at the end of Step 1 (confirming RLS with
  two real test users) and the first live end-to-end query in Session 5
  onward genuinely need real keys present. Everything before that is safe
  to build blind.
- When the agent's turn requires a live call and the key isn't set, it
  should fail with a clear "SUPABASE_URL not set" error and stop — not
  fabricate a placeholder key and pretend the call succeeded.

### Step 3 — Repo scaffold
Create the folder structure in §3 below, empty files where noted. Init git, first commit.

### Step 4 — Backend bootstrap
1. Create and activate a virtual environment, then install dependencies from `backend/requirements.txt` (already provided in this repo — no need to write it yourself):
   ```bash
   cd backend
   python -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
2. `backend/app/core/config.py` reading env vars (see §4).
3. `backend/app/main.py` — FastAPI app with a `/health` route. Get this running (`uvicorn app.main:app --reload`) before writing anything else.

If a new dependency is needed later, add it to `backend/requirements.txt` with a pinned version (not a bare `pip install` left undocumented) and re-run `pip install -r requirements.txt` — keep the file as the single source of truth for what the environment needs, since that's what makes a fresh `venv` reproducible for you or anyone else picking this up.

### Step 5 — Frontend bootstrap
1. `npx create-next-app@latest frontend --typescript --tailwind --app`
2. Install `@supabase/supabase-js` and `@supabase/ssr` for the Supabase Auth client.
3. Get a blank page rendering before writing real UI.

### Step 6 — First vertical slice
Follow `docs/Lean-Backlog.md` starting at L1.1. Don't build ahead of the current ticket — each one is scoped to leave you with something runnable.

---

## 3. Folder Structure

```text
askyourdata/
├── README.md
├── docs/
│   ├── Lean-MVP-Scope.md
│   ├── Lean-Backlog.md
│   ├── PRD.md, SRS.md, System-Architecture.md, UIUX.md,
│   │   Development-Plan.md, Backlog.md, Repo-Scaffold.md   (full-spec reference)
│   └── Project-Description.md
│
├── schemas/
│   └── query-ir.schema.json          # planner ↔ execution contract, unchanged
│
├── api/
│   └── openapi.yaml                  # full contract; lean build implements a subset
│
├── db/
│   ├── schema.sql                    # full-spec reference schema
│   └── schema-lean.sql               # ← what you actually apply to Supabase now
│
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── Dockerfile
│   └── app/
│       ├── main.py                   # FastAPI app entrypoint, mounts routers below
│       │
│       ├── core/
│       │   ├── config.py             # env-driven settings (Settings class)
│       │   ├── security.py           # verifies Supabase-issued JWT, extracts user_id
│       │   ├── supabase_client.py    # two clients: anon (RLS-respecting, per-request)
│       │   │                         #   and service-role (trusted paths only)
│       │   └── logging.py            # request_id generation + structured logging
│       │
│       ├── api/                      # one module per resource, per api/openapi.yaml subset
│       │   ├── workspaces.py         # POST/GET /workspaces
│       │   ├── files.py              # POST /workspaces/{id}/files, GET .../{file_id}
│       │   ├── catalog.py            # GET /catalog/tables, /catalog/tables/{id}
│       │   ├── query.py              # POST /workspaces/{id}/query, GET .../history
│       │   └── me.py                 # POST/GET/DELETE /me/groq-key — per-user key management
│       │
│       ├── ingestion/
│       │   ├── validators.py         # CSV file type/size checks (5MB cap for lean scope)
│       │   ├── parser.py             # CSV parsing (pandas or csv module)
│       │   ├── schema_inference.py   # column types, nullability, sample values
│       │   └── storage.py            # Supabase Storage upload/fetch helpers
│       │
│       ├── catalog/
│       │   └── service.py            # reads/writes catalog_tables, catalog_columns
│       │
│       ├── llm/
│       │   ├── provider_interface.py # LLMProvider ABC: generate(user_id, purpose, input, schema)
│       │   │                        #   — takes user_id so the adapter fetches THAT user's key
│       │   ├── key_store.py          # encrypt/decrypt/fetch per-user Groq key (uses ENCRYPTION_KEY)
│       │   ├── adapters/
│       │   │   └── groq_adapter.py   # the one adapter for lean scope — uses the `openai`
│       │   │                        #   package, base_url=GROQ_BASE_URL, api_key=caller's own key
│       │   ├── prompts/
│       │   │   └── query_planning_v1.yaml
│       │   └── schemas/
│       │       └── query_planning_output.schema.json
│       │
│       ├── ir/
│       │   └── validator.py          # validates planner output against
│       │                             #   schemas/query-ir.schema.json (structured kind only)
│       │
│       ├── execution/
│       │   ├── duckdb_backend.py     # compiles validated IR -> DuckDB SQL, executes
│       │   └── safety_validator.py   # rejects write/DDL keywords — never skip this
│       │
│       ├── query_pipeline/
│       │   ├── orchestrator.py       # the L4-L6 sequence: validate -> execute ->
│       │   │                         #   repair (max 1 attempt) -> respond
│       │   └── repair.py
│       │
│       └── db/
│           └── models.py             # Pydantic models mirroring db/schema-lean.sql
│
├── frontend/
│   ├── package.json
│   ├── .env.local.example
│   ├── Dockerfile
│   └── app/
│       ├── layout.tsx
│       ├── (auth)/
│       │   ├── login/page.tsx
│       │   └── signup/page.tsx
│       ├── workspace/[workspaceId]/
│       │   ├── page.tsx              # upload + dataset preview (Session 3)
│       │   └── chat/page.tsx         # question -> answer card (Session 6)
│       ├── settings/
│       │   └── page.tsx              # per-user Groq API key entry (Session 5, L5.0F)
│       ├── components/
│       │   ├── upload/
│       │   ├── catalog/
│       │   ├── settings/
│       │   │   └── ApiKeyForm.tsx    # masked input, "configured ✓" state, save/remove
│       │   └── chat/
│       │       └── AnswerCard.tsx    # text + result table + "View SQL"
│       └── lib/
│           ├── supabase-client.ts    # browser Supabase client (anon key)
│           └── api-client.ts         # typed fetch wrapper for the FastAPI backend
│
└── infra/
    └── docker-compose.yml            # backend + frontend only (see §4)
```

Everything from the full-spec `Repo-Scaffold.md` that isn't listed above
(pandas_backend/, governance/, audit/, workers/, etc.) is simply not created
yet — add those directories when you pick up the corresponding ticket from
the full `docs/Backlog.md` later. Don't pre-create empty placeholders for
lean scope; it adds noise for no benefit at this size.

---

## 4. Environment Variables

**Two files per app, not one:**
- `.env.example` (backend) / `.env.local.example` (frontend) — **committed to git**, every variable name present with a placeholder or empty value. The agent creates and edits these freely.
- `.env` (backend) / `.env.local` (frontend) — **gitignored, never committed, never pasted into the agent conversation.** You create these yourself by copying the `.example` file and filling in real values directly in your editor/terminal, outside the chat.

`backend/.env.example`:
```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=

# Groq base URL is platform-wide (same endpoint for everyone); the API key
# itself is NOT set here — each user provides their own via the Settings
# page (L5.0), stored encrypted per-user in the database, not in this file.
GROQ_BASE_URL=

# Symmetric key used to encrypt/decrypt every user's stored Groq API key
# (see L5.0). Generate once with, e.g.:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Losing this key means every stored user API key becomes unrecoverable —
# back it up somewhere safe, separate from the .env file itself.
ENCRYPTION_KEY=

MAX_QUERY_REPAIR_ATTEMPTS=1
MAX_FILE_SIZE_MB=5
MAX_ROWS_SCANNED=1000000
QUERY_TIMEOUT_SECONDS=10
```

`frontend/.env.local.example`:
```text
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Add to `.gitignore` at repo root, first commit, before anything else:
```text
.env
.env.local
```

`infra/docker-compose.yml`:
```yaml
services:
  backend:
    build: ../backend
    env_file: ../backend/.env
    ports: ["8000:8000"]

  frontend:
    build: ../frontend
    env_file: ../frontend/.env.local
    ports: ["3000:3000"]
    depends_on: [backend]
```

No Postgres or Redis service — Supabase is the database, and lean scope has
no caching layer.

---

## 5. First Thing To Actually Run

Before any ticket work, confirm the skeleton is alive. This step assumes
you've already filled in your real `.env`/`.env.local` yourself (§4) —
the agent should not be the one entering those values.

```bash
# Backend
cd backend && uvicorn app.main:app --reload
curl http://localhost:8000/health   # should return 200

# Frontend
cd frontend && npm run dev
# visit localhost:3000, should render without errors
```

Once both of those work, start `docs/Lean-Backlog.md` at L1.1.

---

## 6. Secrets Policy (read this before starting any session)

- **Never** type a Supabase key, `service_role` key, database password, or
  Groq API key into the agent conversation, even to "just get it working
  faster." The agent doesn't need to see the value to write code that reads
  it from an environment variable.
- If the agent asks you for a real key/URL directly in chat, decline and
  instead go fill in the `.env`/`.env.local` file yourself, then tell the
  agent "the env file is populated, continue."
- If a ticket genuinely can't be verified without a live credential (e.g.
  the RLS test in Step 1, or the first real Groq API call in Session 5), the
  agent should tell you what it needs set and pause — not prompt you to
  paste the value into chat, and not proceed with a fabricated placeholder
  pretending it succeeded.
- `.env` and `.env.local` must be in `.gitignore` from the very first
  commit. If you're using Antigravity's own credential/secrets storage
  feature (if it has one) instead of local `.env` files, the same rule
  applies: the agent configures *where* secrets are read from, you supply
  the actual values through whatever out-of-band mechanism the tool offers.
