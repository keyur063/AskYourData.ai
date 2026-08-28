-- AskYourData.ai — Metadata Database Schema (Supabase / PostgreSQL)
--
-- SUPABASE NOTES (read before applying):
-- * Auth is delegated to Supabase Auth. auth.users is managed by Supabase —
--   do NOT create a custom `users` table with its own id sequence. Instead
--   `public.users` below is a 1:1 profile table keyed on auth.users.id,
--   kept in sync via a trigger (see bottom of file).
-- * RLS policies use auth.uid() directly (Supabase sets this from the JWT
--   automatically on every request) joined through workspace_members —
--   this replaces the manually-set `app.current_workspace_ids` session
--   variable from the original design. Simpler and less error-prone: there
--   is no per-request setup step the API layer can forget to do.
-- * File storage: use Supabase Storage (bucket per workspace or a single
--   bucket with workspace-prefixed paths + Storage RLS policies) instead of
--   a separate S3-compatible service. Storage policies follow the same
--   auth.uid()-via-workspace_members pattern as the tables below.
-- * Credential encryption: use Supabase Vault (pgsodium-backed) for
--   `encrypted_credential` instead of an external KMS, or keep an external
--   KMS if you have one already — either is fine, Vault is just one less
--   moving piece.

create extension if not exists "pgcrypto";  -- for gen_random_uuid()

-- =========================================================================
-- Core identity & workspace tables
-- =========================================================================

-- Profile table 1:1 with Supabase's auth.users. Do not store password
-- hashes or SSO details here — Supabase Auth owns credentials entirely.
create table public.users (
    id              uuid primary key references auth.users(id) on delete cascade,
    email           text not null unique,
    name            text,
    created_at      timestamptz not null default now(),
    disabled_at     timestamptz
);

-- Keeps public.users in sync whenever Supabase Auth creates a new user.
create function public.handle_new_auth_user()
returns trigger as $$
begin
    insert into public.users (id, email)
    values (new.id, new.email);
    return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_auth_user();

create table workspaces (
    id              uuid primary key default gen_random_uuid(),
    name            text not null,
    created_by      uuid not null references users(id),
    created_at      timestamptz not null default now(),
    deleted_at      timestamptz          -- soft delete; hard delete via retention job
);

create type workspace_role as enum ('owner', 'editor', 'analyst', 'viewer');

create table workspace_members (
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    user_id         uuid not null references users(id) on delete cascade,
    role            workspace_role not null,
    joined_at       timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

create type plan_tier as enum ('free', 'pro', 'enterprise');

create table entitlements (
    workspace_id            uuid primary key references workspaces(id) on delete cascade,
    plan                    plan_tier not null default 'free',
    queries_per_minute      integer not null default 10,
    queries_per_day         integer not null default 100,
    max_file_size_mb        integer not null default 50,
    max_rows_per_file       integer not null default 1000000,
    feature_flags           jsonb not null default '{}',
    updated_at              timestamptz not null default now()
);

-- =========================================================================
-- Data sources: files and database connections
-- =========================================================================

create type file_state as enum ('UPLOADING', 'PROCESSING', 'READY', 'FAILED', 'DELETING');

create table files (
    id                  uuid primary key default gen_random_uuid(),
    workspace_id        uuid not null references workspaces(id) on delete cascade,
    filename            text not null,
    object_storage_key  text not null,
    content_hash        text not null,        -- SHA-256, drives dataset_version
    file_type           text not null,        -- csv | xlsx
    size_bytes          bigint not null,
    state               file_state not null default 'UPLOADING',
    error_message       text,
    uploaded_by         uuid not null references users(id),
    created_at          timestamptz not null default now(),
    ready_at            timestamptz,
    unique (workspace_id, content_hash)
);

create type ds_type as enum ('postgresql', 'mysql', 'sqlserver');
create type ds_status as enum ('ACTIVE', 'ERROR', 'TESTING');

create table data_sources (
    id                      uuid primary key default gen_random_uuid(),
    workspace_id            uuid not null references workspaces(id) on delete cascade,
    type                    ds_type not null,
    host                    text not null,
    port                    integer not null,
    database_name           text not null,
    username                text not null,
    encrypted_credential    bytea not null,     -- envelope-encrypted via Supabase Vault (or external KMS)
    kms_key_id              text not null,      -- Vault secret/key reference, or external KMS key id
    ssl                     boolean not null default true,
    read_only_verified      boolean not null default false,
    status                  ds_status not null default 'TESTING',
    last_schema_refresh_at  timestamptz,
    created_by              uuid not null references users(id),
    created_at              timestamptz not null default now()
);

-- =========================================================================
-- Data Catalog
-- =========================================================================

create table datasets (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    file_id         uuid references files(id) on delete cascade,
    data_source_id  uuid references data_sources(id) on delete cascade,
    version         text not null,             -- content hash (files) or schema-diff hash (DBs)
    created_at      timestamptz not null default now(),
    check (
        (file_id is not null and data_source_id is null) or
        (file_id is null and data_source_id is not null)
    )
);

create table catalog_tables (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    dataset_id      uuid not null references datasets(id) on delete cascade,
    name            text not null,             -- workspace-scoped logical table name
    source_object   text,                      -- original sheet name / DB table name
    description     text,
    row_count       bigint,
    created_at      timestamptz not null default now(),
    unique (workspace_id, name)
);

create type semantic_type as enum (
    'identifier','currency','date','datetime','percentage',
    'category','location','email','name','numeric','text','boolean'
);

create table catalog_columns (
    id                  uuid primary key default gen_random_uuid(),
    workspace_id        uuid not null references workspaces(id) on delete cascade,
    table_id            uuid not null references catalog_tables(id) on delete cascade,
    name                text not null,
    data_type           text not null,
    nullable            boolean not null default true,
    unique_count         bigint,
    null_percentage      numeric(5,2),
    sample_values        jsonb,
    min_value             text,
    max_value             text,
    semantic_type         semantic_type,
    description           text,
    pii_flag               boolean not null default false,
    pii_category            text,               -- e.g. 'email', 'name', 'phone', 'gov_id'
    unique (table_id, name)
);

create table relationships (
    id                  uuid primary key default gen_random_uuid(),
    workspace_id        uuid not null references workspaces(id) on delete cascade,
    source_column_id    uuid not null references catalog_columns(id) on delete cascade,
    target_column_id    uuid not null references catalog_columns(id) on delete cascade,
    confidence           numeric(4,3) not null,
    detection_method      text not null,        -- 'name_similarity' | 'value_overlap' | 'llm_assisted' | 'manual'
    created_at             timestamptz not null default now()
);

-- =========================================================================
-- Semantic layer
-- =========================================================================

create table metrics (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    name            text not null,
    definition      text not null,          -- e.g. 'SUM(quantity * unit_price)'
    description     text,
    created_by      uuid not null references users(id),
    created_at      timestamptz not null default now(),
    unique (workspace_id, name)
);

-- =========================================================================
-- Query history, results, LLM usage
-- =========================================================================

create table query_threads (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    created_by      uuid not null references users(id),
    created_at      timestamptz not null default now()
);

create type query_status as enum ('answered', 'needs_clarification', 'failed');
create type answer_source as enum ('deterministic', 'llm_generated');

create table query_history (
    request_id          uuid primary key default gen_random_uuid(),
    workspace_id         uuid not null references workspaces(id) on delete cascade,
    thread_id             uuid references query_threads(id) on delete set null,
    user_id                uuid not null references users(id),
    question                text not null,
    normalized_question      text not null,
    status                    query_status not null,
    answer_source              answer_source,
    query_ir                   jsonb,          -- see schemas/query-ir.schema.json
    generated_sql               text,
    error_message                 text,
    execution_time_ms              integer,
    cache_hit                       boolean not null default false,
    created_at                       timestamptz not null default now()
);

create table query_results (
    request_id          uuid primary key references query_history(request_id) on delete cascade,
    result_columns        jsonb not null,
    result_rows            jsonb not null,     -- consider external/object storage for very large results
    row_count                integer,
    chart_type                 text,
    chart_spec                   jsonb
);

create table llm_usage (
    id                  uuid primary key default gen_random_uuid(),
    request_id           uuid references query_history(request_id) on delete set null,
    workspace_id           uuid not null references workspaces(id) on delete cascade,
    user_id                  uuid references users(id),
    provider                   text not null,     -- 'anthropic' | 'openai' | ...
    model                        text not null,
    purpose                        text not null,   -- 'query_planning' | 'query_repair' | 'answer_generation' | ...
    input_tokens                     integer,
    output_tokens                      integer,
    latency_ms                          integer,
    estimated_cost_usd                    numeric(10,6),
    created_at                              timestamptz not null default now()
);

create table audit_log (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    user_id         uuid references users(id),
    action          text not null,       -- 'login' | 'connection_created' | 'file_uploaded' | 'query_executed' | 'member_role_changed' | ...
    resource_type   text,
    resource_id     text,
    role_at_time    workspace_role,
    ip              inet,
    metadata        jsonb,
    created_at      timestamptz not null default now()
);

-- =========================================================================
-- Indexes
-- =========================================================================

create index idx_workspace_members_user       on workspace_members(user_id);
create index idx_files_workspace                on files(workspace_id);
create index idx_data_sources_workspace          on data_sources(workspace_id);
create index idx_catalog_tables_workspace          on catalog_tables(workspace_id);
create index idx_catalog_columns_table               on catalog_columns(table_id);
create index idx_catalog_columns_pii                   on catalog_columns(workspace_id) where pii_flag = true;
create index idx_relationships_workspace                 on relationships(workspace_id);
create index idx_query_history_workspace_created           on query_history(workspace_id, created_at desc);
create index idx_query_history_normalized                    on query_history(workspace_id, normalized_question);
create index idx_llm_usage_workspace_created                   on llm_usage(workspace_id, created_at desc);
create index idx_audit_log_workspace_created                     on audit_log(workspace_id, created_at desc);

-- =========================================================================
-- Row-Level Security (Supabase pattern)
--
-- Supabase automatically makes the calling user's id available as
-- auth.uid() inside every policy, taken from the request's JWT — no manual
-- session-variable setup required in the API layer (this replaces the
-- app.current_user_id / app.current_workspace_ids approach from the
-- generic-Postgres version of this schema).
--
-- Helper function: is the current auth.uid() a member of a given workspace?
-- Defined once, reused across every policy below — keeps policies short and
-- keeps the membership-lookup logic in exactly one place.
-- =========================================================================

create function public.is_workspace_member(target_workspace_id uuid)
returns boolean as $$
    select exists (
        select 1 from public.workspace_members wm
        where wm.workspace_id = target_workspace_id
          and wm.user_id = auth.uid()
    );
$$ language sql security definer stable;

-- Same idea, but also checks minimum role (owner > editor > analyst > viewer).
create function public.has_workspace_role(target_workspace_id uuid, min_role workspace_role)
returns boolean as $$
    select exists (
        select 1 from public.workspace_members wm
        where wm.workspace_id = target_workspace_id
          and wm.user_id = auth.uid()
          and (
                (min_role = 'viewer') or
                (min_role = 'analyst' and wm.role in ('analyst','editor','owner')) or
                (min_role = 'editor'  and wm.role in ('editor','owner')) or
                (min_role = 'owner'   and wm.role = 'owner')
              )
    );
$$ language sql security definer stable;

alter table workspaces          enable row level security;
alter table workspace_members   enable row level security;
alter table entitlements        enable row level security;
alter table files               enable row level security;
alter table data_sources        enable row level security;
alter table datasets            enable row level security;
alter table catalog_tables      enable row level security;
alter table catalog_columns     enable row level security;
alter table relationships       enable row level security;
alter table metrics             enable row level security;
alter table query_threads       enable row level security;
alter table query_history       enable row level security;
alter table query_results       enable row level security;
alter table llm_usage           enable row level security;
alter table audit_log           enable row level security;

create policy workspace_isolation_workspaces on workspaces
    for select using (public.is_workspace_member(id));

create policy workspace_isolation_workspace_members on workspace_members
    for select using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_entitlements on entitlements
    for select using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_files on files
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_data_sources on data_sources
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_datasets on datasets
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_catalog_tables on catalog_tables
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_catalog_columns on catalog_columns
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_relationships on relationships
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_metrics on metrics
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_query_threads on query_threads
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_query_history on query_history
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_query_results on query_results
    using (
        exists (
            select 1 from public.query_history qh
            where qh.request_id = query_results.request_id
              and public.is_workspace_member(qh.workspace_id)
        )
    );

create policy workspace_isolation_llm_usage on llm_usage
    using (public.is_workspace_member(workspace_id));

create policy workspace_isolation_audit_log on audit_log
    using (public.has_workspace_role(workspace_id, 'owner'));

-- Write policies (insert/update/delete) are intentionally separate from the
-- blanket `using` policies above, which currently cover SELECT via the
-- default `for all` behavior on `using` alone in Postgres RLS — confirm
-- during implementation whether you want `for all` (read+write same rule)
-- or split into explicit `for select` / `for insert` / `for update` /
-- `for delete` per table so that, e.g., only editor+ can insert into
-- `files` while analyst+ can only select. Role-gated write policies
-- (using has_workspace_role) should be added per table per the SRS
-- FR-AUTH-3/4 role matrix before Phase 0 is considered complete.
