-- AskYourData.ai — Lean MVP Schema (Supabase / PostgreSQL)
-- Trimmed to 8 tables per docs/Lean-MVP-Scope.md §4. Two roles only
-- (owner, member) instead of the full 4-tier RBAC. CSV-only ingestion,
-- single-table queries, no PII/audit/semantic-layer/caching tables.
--
-- See db/schema.sql for the full version — nothing here conflicts with it;
-- this is a subset you can grow into the full schema later by adding
-- tables/columns, not by changing what already exists.

create extension if not exists "pgcrypto";

-- =========================================================================
-- Identity & workspace
-- =========================================================================

create table public.users (
    id              uuid primary key references auth.users(id) on delete cascade,
    email           text not null unique,
    name            text,
    created_at      timestamptz not null default now()
);

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
    created_by      uuid not null references public.users(id),
    created_at      timestamptz not null default now()
);

create type workspace_role as enum ('owner', 'member');

create table workspace_members (
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    user_id         uuid not null references public.users(id) on delete cascade,
    role            workspace_role not null default 'member',
    joined_at       timestamptz not null default now(),
    primary key (workspace_id, user_id)
);

-- Auto-add creator as owner
create function public.handle_new_workspace()
returns trigger as $$
begin
    insert into public.workspace_members (workspace_id, user_id, role)
    values (new.id, new.created_by, 'owner');
    return new;
end;
$$ language plpgsql security definer;

create trigger on_workspace_created
    after insert on workspaces
    for each row execute function public.handle_new_workspace();

-- =========================================================================
-- Files (CSV only for lean scope) + Catalog
-- =========================================================================

create type file_state as enum ('UPLOADING', 'PROCESSING', 'READY', 'FAILED');

create table files (
    id                  uuid primary key default gen_random_uuid(),
    workspace_id        uuid not null references workspaces(id) on delete cascade,
    filename            text not null,
    storage_path        text not null,      -- Supabase Storage path: {workspace_id}/{content_hash}/{filename}
    content_hash        text not null,
    size_bytes          bigint not null,
    row_count           bigint,
    state               file_state not null default 'UPLOADING',
    error_message       text,
    uploaded_by         uuid not null references public.users(id),
    created_at          timestamptz not null default now(),
    unique (workspace_id, content_hash)
);

create table catalog_tables (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    file_id         uuid not null references files(id) on delete cascade,
    name            text not null,        -- workspace-scoped logical table name (from filename)
    row_count       bigint,
    created_at      timestamptz not null default now(),
    unique (workspace_id, name)
);

create table catalog_columns (
    id              uuid primary key default gen_random_uuid(),
    workspace_id    uuid not null references workspaces(id) on delete cascade,
    table_id        uuid not null references catalog_tables(id) on delete cascade,
    name            text not null,
    data_type       text not null,
    nullable        boolean not null default true,
    sample_values   jsonb,
    unique (table_id, name)
);

-- =========================================================================
-- Query history (includes IR + generated SQL + result, folded together
-- for lean scope instead of a separate query_results table)
-- =========================================================================

create type query_status as enum ('answered', 'failed');

create table query_history (
    request_id          uuid primary key default gen_random_uuid(),
    workspace_id        uuid not null references workspaces(id) on delete cascade,
    user_id             uuid not null references public.users(id),
    question            text not null,
    status              query_status not null,
    query_ir            jsonb,       -- see schemas/query-ir.schema.json
    generated_sql       text,
    result_columns      jsonb,
    result_rows         jsonb,
    error_message       text,
    created_at          timestamptz not null default now()
);

create table llm_usage (
    id                  uuid primary key default gen_random_uuid(),
    request_id          uuid references query_history(request_id) on delete set null,
    workspace_id        uuid not null references workspaces(id) on delete cascade,
    provider            text not null,
    model               text not null,
    purpose             text not null,
    input_tokens        integer,
    output_tokens       integer,
    estimated_cost_usd  numeric(10,6),
    created_at          timestamptz not null default now()
);

-- =========================================================================
-- Row-Level Security
-- =========================================================================

create function public.is_workspace_member(target_workspace_id uuid)
returns boolean as $$
    select exists (
        select 1 from public.workspace_members wm
        where wm.workspace_id = target_workspace_id
          and wm.user_id = auth.uid()
    );
$$ language sql security definer stable;

alter table public.users       enable row level security;
alter table workspaces         enable row level security;
alter table workspace_members  enable row level security;
alter table files              enable row level security;
alter table catalog_tables     enable row level security;
alter table catalog_columns    enable row level security;
alter table query_history      enable row level security;
alter table llm_usage          enable row level security;

-- users has no workspace_id (it's a global profile table, one row per
-- person), so it can't use is_workspace_member() directly like every other
-- table below. Instead: a user can always see their own row, and can see
-- the profile (name/email) of anyone who shares at least one workspace
-- with them — needed so member-list UIs can show co-members' names/emails.
-- Insert happens only via the handle_new_auth_user() trigger (security
-- definer, bypasses RLS) — no insert/update/delete policy needed yet.
create policy users_self_and_co_members on public.users
    for select using (
        id = auth.uid()
        or exists (
            select 1
            from public.workspace_members my_ws
            join public.workspace_members shared_ws
              on shared_ws.workspace_id = my_ws.workspace_id
            where my_ws.user_id = auth.uid()
              and shared_ws.user_id = users.id
        )
    );

create policy ws_isolation_workspaces on workspaces
    for select using (public.is_workspace_member(id));

create policy ws_isolation_members on workspace_members
    for select using (public.is_workspace_member(workspace_id));

create policy ws_isolation_files on files
    using (public.is_workspace_member(workspace_id));

create policy ws_isolation_catalog_tables on catalog_tables
    using (public.is_workspace_member(workspace_id));

create policy ws_isolation_catalog_columns on catalog_columns
    using (public.is_workspace_member(workspace_id));

create policy ws_isolation_query_history on query_history
    using (public.is_workspace_member(workspace_id));

create policy ws_isolation_llm_usage on llm_usage
    using (public.is_workspace_member(workspace_id));

-- NOTE: as with the full schema, these `using` clauses cover all commands
-- (select/insert/update/delete) by default. For lean scope this is
-- acceptable (both roles can read/write within their own workspace); add
-- role-gated write policies (owner vs member) only if/when you need that
-- distinction to matter — not required for the lean MVP to be safe.
