"use client";

import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/app/lib/supabase-client";
import { apiClient } from "@/app/lib/api-client";

interface Workspace {
  id: string;
  name: string;
  created_by: string;
  created_at: string;
}

export default function DashboardPage() {
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadWorkspaces = useCallback(async () => {
    try {
      const ws = await apiClient.get<Workspace[]>("/workspaces");
      setWorkspaces(ws);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load workspaces");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.replace("/login");
        return;
      }
      loadWorkspaces();
    });
  }, [router, loadWorkspaces]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    setError(null);
    try {
      await apiClient.post<Workspace>("/workspaces", { name: newName.trim() });
      setNewName("");
      setShowCreate(false);
      await loadWorkspaces();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create workspace");
    } finally {
      setCreating(false);
    }
  }

  async function handleSignOut() {
    await supabase.auth.signOut();
    router.replace("/login");
  }

  return (
    <div className="flex min-h-full flex-col">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-6">
          <h1 className="text-lg font-bold tracking-tight">
            Ask<span className="text-accent">YourData</span>
          </h1>
          <button
            onClick={handleSignOut}
            className="rounded-lg px-3 py-1.5 text-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-bold text-text-primary">Workspaces</h2>
            <p className="mt-1 text-sm text-text-secondary">
              Each workspace holds one or more CSV datasets
            </p>
          </div>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white hover:bg-accent-hover"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="shrink-0">
              <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
            New workspace
          </button>
        </div>

        {/* Create form */}
        {showCreate && (
          <form
            onSubmit={handleCreate}
            className="mb-8 flex gap-3 rounded-xl border border-border bg-surface p-4"
          >
            <input
              type="text"
              required
              maxLength={200}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Workspace name..."
              className="flex-1 rounded-lg border border-border bg-background px-3.5 py-2 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              autoFocus
            />
            <button
              type="submit"
              disabled={creating}
              className="rounded-lg bg-accent px-5 py-2 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
            >
              {creating ? "Creating..." : "Create"}
            </button>
            <button
              type="button"
              onClick={() => setShowCreate(false)}
              className="rounded-lg px-3 py-2 text-sm text-text-secondary hover:bg-surface-hover"
            >
              Cancel
            </button>
          </form>
        )}

        {error && (
          <div className="mb-6 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        ) : workspaces.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border py-20 text-center">
            <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-accent-muted">
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none">
                <path
                  d="M3 7l9-4 9 4v10l-9 4-9-4V7z"
                  stroke="currentColor"
                  strokeWidth="1.5"
                  className="text-accent"
                />
                <path d="M3 7l9 4m0 0l9-4m-9 4v10" stroke="currentColor" strokeWidth="1.5" className="text-accent" />
              </svg>
            </div>
            <p className="text-sm text-text-secondary">No workspaces yet</p>
            <p className="mt-1 text-xs text-text-tertiary">
              Create your first workspace to start uploading data
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {workspaces.map((ws) => (
              <button
                key={ws.id}
                onClick={() => router.push(`/workspace/${ws.id}`)}
                className="group rounded-xl border border-border bg-surface p-5 text-left hover:border-accent/40 hover:bg-surface-hover"
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-accent-muted">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M3 7l9-4 9 4v10l-9 4-9-4V7z"
                      stroke="currentColor"
                      strokeWidth="1.5"
                      className="text-accent"
                    />
                  </svg>
                </div>
                <h3 className="font-semibold text-text-primary group-hover:text-accent">
                  {ws.name}
                </h3>
                <p className="mt-1 text-xs text-text-tertiary">
                  Created {new Date(ws.created_at).toLocaleDateString()}
                </p>
              </button>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
