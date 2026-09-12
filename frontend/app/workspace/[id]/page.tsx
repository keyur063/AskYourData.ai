"use client";

import { useEffect, useState, useCallback, use, useRef } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/app/lib/supabase-client";
import { apiClient } from "@/app/lib/api-client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FileRecord {
  id: string;
  workspace_id: string;
  filename: string;
  size_bytes: number;
  row_count: number | null;
  state: string;
  created_at: string;
}

interface CatalogColumn {
  id: string;
  name: string;
  data_type: string;
  nullable: boolean;
  sample_values: string | null;
}

interface CatalogTable {
  id: string;
  name: string;
  row_count: number | null;
  file_id: string;
  columns: CatalogColumn[];
}

interface KeyStatus {
  configured: boolean;
  model: string | null;
}

interface QueryResult {
  columns: string[];
  rows: unknown[][];
  sql: string;
  confidence: number;
  repaired?: boolean;
  fallback?: boolean;
  message?: string;
}

interface ChatMessage {
  id: string;
  question: string;
  result: QueryResult | null;
  error: string | null;
  loading: boolean;
  showSql: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function WorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: workspaceId } = use(params);
  const router = useRouter();

  // Data state
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [tables, setTables] = useState<CatalogTable[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<CatalogTable | null>(null);
  const [keyStatus, setKeyStatus] = useState<KeyStatus | null>(null);

  // UI state
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState(false);

  // Chat state
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [querying, setQuerying] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ---------------------------------------------------------------------------
  // Data loading
  // ---------------------------------------------------------------------------

  const loadData = useCallback(async () => {
    try {
      const [filesRes, tablesRes, keyRes] = await Promise.all([
        apiClient.get<FileRecord[]>(`/workspaces/${workspaceId}/files`),
        apiClient.get<CatalogTable[]>(`/workspaces/${workspaceId}/catalog/tables`),
        apiClient.get<KeyStatus>("/me/groq-key"),
      ]);
      setFiles(filesRes);
      setTables(tablesRes);
      setKeyStatus(keyRes);
      if (tablesRes.length > 0 && !selectedTableId) {
        setSelectedTableId(tablesRes[0].id);
      }
    } catch {
      // silently fail on initial load
    } finally {
      setLoading(false);
    }
  }, [workspaceId, selectedTableId]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.replace("/login"); return; }
      loadData();
    });
  }, [router, loadData]);

  useEffect(() => {
    if (!selectedTableId) return;
    apiClient
      .get<CatalogTable>(`/workspaces/${workspaceId}/catalog/tables/${selectedTableId}`)
      .then(setSelectedTable)
      .catch(() => setSelectedTable(null));
  }, [workspaceId, selectedTableId]);

  // Scroll chat to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ---------------------------------------------------------------------------
  // Upload handlers
  // ---------------------------------------------------------------------------

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      await apiClient.uploadFile<FileRecord>(`/workspaces/${workspaceId}/files`, file);
      await loadData();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleUpload(file);
    e.target.value = "";
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleUpload(file);
  }

  // ---------------------------------------------------------------------------
  // Chat / query handlers
  // ---------------------------------------------------------------------------

  async function handleQuery(e: React.FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q || !selectedTableId || querying) return;

    const msgId = Date.now().toString();
    const newMsg: ChatMessage = {
      id: msgId,
      question: q,
      result: null,
      error: null,
      loading: true,
      showSql: false,
    };

    setMessages((prev) => [...prev, newMsg]);
    setQuestion("");
    setQuerying(true);

    try {
      const data = await apiClient.post<QueryResult>(
        `/workspaces/${workspaceId}/query`,
        { question: q, table_id: selectedTableId }
      );
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, loading: false, result: data } : m
        )
      );
    } catch (err) {
      const errMsg = err instanceof Error ? err.message : "Query failed";
      setMessages((prev) =>
        prev.map((m) =>
          m.id === msgId ? { ...m, loading: false, error: errMsg } : m
        )
      );
    } finally {
      setQuerying(false);
    }
  }

  function toggleSql(id: string) {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, showSql: !m.showSql } : m))
    );
  }

  // ---------------------------------------------------------------------------
  // Formatters
  // ---------------------------------------------------------------------------

  function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function parseSamples(sv: string | null): string[] {
    if (!sv) return [];
    try {
      const arr = JSON.parse(sv);
      return Array.isArray(arr) ? arr.map(String) : [];
    } catch { return []; }
  }

  const typeColor: Record<string, string> = {
    text: "text-emerald-400",
    integer: "text-blue-400",
    float: "text-cyan-400",
    boolean: "text-amber-400",
    datetime: "text-purple-400",
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="flex min-h-full flex-col">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-6">
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0">
              <path d="M10 12L6 8l4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Back
          </button>
          <div className="h-4 w-px bg-border" />
          <h1 className="text-sm font-semibold text-text-primary">Workspace</h1>
          <div className="ml-auto">
            <button
              onClick={() => router.push("/settings")}
              className="rounded-lg px-3 py-1.5 text-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            >
              Settings
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">

        {/* ── Upload area ── */}
        <div
          className={`mb-8 rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
            dragOver ? "border-accent bg-accent-muted" : "border-border hover:border-accent/40"
          }`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <div className="mb-3 flex justify-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-muted">
              {uploading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              ) : (
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M10 14V3m0 0L6 7m4-4l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-accent" />
                  <path d="M3 14v1a2 2 0 002 2h10a2 2 0 002-2v-1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="text-accent" />
                </svg>
              )}
            </div>
          </div>
          <p className="text-sm font-medium text-text-primary">
            {uploading ? "Uploading..." : "Drop a CSV file here or"}
          </p>
          {!uploading && (
            <label className="mt-2 inline-block cursor-pointer rounded-lg bg-accent px-4 py-1.5 text-xs font-medium text-white hover:bg-accent-hover">
              Browse files
              <input type="file" accept=".csv" onChange={handleFileInput} className="hidden" />
            </label>
          )}
          <p className="mt-2 text-xs text-text-tertiary">CSV files up to 5 MB</p>
        </div>

        {uploadError && (
          <div className="mb-6 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
            {uploadError}
          </div>
        )}

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        ) : (
          <>
            {/* ── Files list ── */}
            {files.length > 0 && (
              <div className="mb-8">
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-text-tertiary">
                  Uploaded Files
                </h2>
                <div className="space-y-2">
                  {files.map((f) => {
                    const table = tables.find((t) => t.file_id === f.id);
                    return (
                      <button
                        key={f.id}
                        onClick={() => table && setSelectedTableId(table.id)}
                        className={`flex w-full items-center gap-4 rounded-xl border p-4 text-left transition-colors ${
                          table && selectedTableId === table.id
                            ? "border-accent/50 bg-accent-muted"
                            : "border-border bg-surface hover:bg-surface-hover"
                        }`}
                      >
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-muted">
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <path d="M4 1h5.5L13 4.5V13a2 2 0 01-2 2H5a2 2 0 01-2-2V3a2 2 0 012-2z" stroke="currentColor" strokeWidth="1.2" className="text-accent" />
                          </svg>
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-text-primary">{f.filename}</p>
                          <p className="text-xs text-text-tertiary">
                            {formatBytes(f.size_bytes)}
                            {f.row_count != null && ` · ${f.row_count.toLocaleString()} rows`}
                          </p>
                        </div>
                        <span className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                          f.state === "READY" ? "bg-success/15 text-success"
                          : f.state === "FAILED" ? "bg-error/15 text-error"
                          : "bg-warning/15 text-warning"
                        }`}>
                          {f.state}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ── Schema preview ── */}
            {selectedTable && (
              <div className="mb-8">
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-text-tertiary">
                  Schema Preview —{" "}
                  <span className="normal-case text-text-primary">{selectedTable.name}</span>
                  {selectedTable.row_count != null && (
                    <span className="ml-2 font-normal normal-case text-text-secondary">
                      ({selectedTable.row_count.toLocaleString()} rows)
                    </span>
                  )}
                </h2>
                <div className="overflow-hidden rounded-xl border border-border">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b border-border bg-surface">
                        {["Column","Type","Nullable","Sample Values"].map((h) => (
                          <th key={h} className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                            {h}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedTable.columns.map((col, i) => {
                        const samples = parseSamples(col.sample_values);
                        return (
                          <tr key={col.id} className={i % 2 === 0 ? "bg-background" : "bg-surface/30"}>
                            <td className="px-4 py-3 font-mono text-xs text-text-primary">{col.name}</td>
                            <td className="px-4 py-3">
                              <span className={`inline-block rounded-md bg-surface px-2 py-0.5 font-mono text-xs ${typeColor[col.data_type] ?? "text-text-secondary"}`}>
                                {col.data_type}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              {col.nullable
                                ? <span className="text-xs text-warning">yes</span>
                                : <span className="text-xs text-text-tertiary">no</span>}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1.5">
                                {samples.slice(0, 4).map((v, j) => (
                                  <span key={j} className="inline-block max-w-[140px] truncate rounded bg-surface px-2 py-0.5 font-mono text-xs text-text-secondary">
                                    {v}
                                  </span>
                                ))}
                                {samples.length > 4 && (
                                  <span className="text-xs text-text-tertiary">+{samples.length - 4}</span>
                                )}
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* ── Chat interface ── */}
            {tables.length > 0 && (
              <div>
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-text-tertiary">
                  Ask a Question
                </h2>

                {/* No API key gate */}
                {keyStatus && !keyStatus.configured ? (
                  <div className="rounded-xl border border-warning/30 bg-warning/5 px-6 py-5">
                    <p className="text-sm font-medium text-warning">No Groq API key configured</p>
                    <p className="mt-1 text-xs text-text-secondary">
                      Add your key in Settings to start querying your data with AI.
                    </p>
                    <button
                      onClick={() => router.push("/settings")}
                      className="mt-3 rounded-lg bg-accent px-4 py-2 text-xs font-medium text-white hover:bg-accent-hover"
                    >
                      Go to Settings →
                    </button>
                  </div>
                ) : (
                  <>
                    {/* Message thread */}
                    {messages.length > 0 && (
                      <div className="mb-4 space-y-4">
                        {messages.map((msg) => (
                          <ChatCard
                            key={msg.id}
                            msg={msg}
                            onToggleSql={() => toggleSql(msg.id)}
                          />
                        ))}
                        <div ref={chatEndRef} />
                      </div>
                    )}

                    {/* Input form */}
                    <form
                      id="query-form"
                      onSubmit={handleQuery}
                      className="flex gap-3"
                    >
                      <input
                        id="question-input"
                        type="text"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        placeholder={
                          selectedTable
                            ? `Ask about ${selectedTable.name}… e.g. "total revenue by region"`
                            : "Select a dataset above, then ask a question…"
                        }
                        disabled={!selectedTableId || querying}
                        className="flex-1 rounded-xl border border-border bg-surface px-4 py-3 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:opacity-50"
                        autoComplete="off"
                      />
                      <button
                        id="query-submit"
                        type="submit"
                        disabled={!selectedTableId || !question.trim() || querying}
                        className="flex items-center gap-2 rounded-xl bg-accent px-5 py-3 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
                      >
                        {querying ? (
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                        ) : (
                          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                            <path d="M2 8h12M10 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                          </svg>
                        )}
                        Ask
                      </button>
                    </form>
                    <p className="mt-2 text-xs text-text-tertiary">
                      Tip: be specific about column names for better results — e.g. "SUM of price by category"
                    </p>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatCard — individual message + result
// ---------------------------------------------------------------------------

function ChatCard({
  msg,
  onToggleSql,
}: {
  msg: ChatMessage;
  onToggleSql: () => void;
}) {
  return (
    <div className="rounded-xl border border-border bg-surface overflow-hidden">
      {/* Question row */}
      <div className="flex items-start gap-3 border-b border-border px-4 py-3">
        <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent-muted text-xs font-bold text-accent">
          Q
        </div>
        <p className="text-sm text-text-primary">{msg.question}</p>
      </div>

      {/* Answer */}
      <div className="px-4 py-4">
        {msg.loading ? (
          <div className="flex items-center gap-2 text-sm text-text-secondary">
            <div className="h-4 w-4 animate-spin rounded-full border-2 border-accent border-t-transparent" />
            Thinking…
          </div>
        ) : msg.error ? (
          <p className="text-sm text-error">{msg.error}</p>
        ) : msg.result?.fallback ? (
          <p className="text-sm text-warning">{msg.result.message}</p>
        ) : msg.result ? (
          <>
            {/* Meta row */}
            <div className="mb-3 flex items-center gap-3">
              {msg.result.repaired && (
                <span className="rounded-full bg-warning/15 px-2.5 py-0.5 text-xs font-medium text-warning">
                  ⚡ Auto-repaired
                </span>
              )}
              <span className="text-xs text-text-tertiary">
                {msg.result.rows.length.toLocaleString()} row{msg.result.rows.length !== 1 ? "s" : ""}
                {" · "}confidence {Math.round(msg.result.confidence * 100)}%
              </span>
              <button
                onClick={onToggleSql}
                className="ml-auto rounded-lg border border-border px-2.5 py-1 text-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
              >
                {msg.showSql ? "Hide SQL" : "View SQL"}
              </button>
            </div>

            {/* SQL panel */}
            {msg.showSql && (
              <pre className="mb-3 overflow-x-auto rounded-lg bg-background p-3 font-mono text-xs text-text-secondary">
                {msg.result.sql}
              </pre>
            )}

            {/* Result table */}
            {msg.result.rows.length === 0 ? (
              <p className="text-sm text-text-tertiary">No results returned.</p>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border bg-background">
                      {msg.result.columns.map((col) => (
                        <th
                          key={col}
                          className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wider text-text-tertiary whitespace-nowrap"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {msg.result.rows.slice(0, 200).map((row, i) => (
                      <tr key={i} className={i % 2 === 0 ? "bg-surface/20" : "bg-surface/40"}>
                        {(row as unknown[]).map((cell, j) => (
                          <td
                            key={j}
                            className="max-w-[240px] truncate px-3 py-2 font-mono text-xs text-text-primary"
                          >
                            {cell == null ? (
                              <span className="text-text-tertiary">null</span>
                            ) : String(cell)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                {msg.result.rows.length > 200 && (
                  <p className="border-t border-border px-3 py-2 text-xs text-text-tertiary">
                    Showing first 200 of {msg.result.rows.length.toLocaleString()} rows
                  </p>
                )}
              </div>
            )}
          </>
        ) : null}
      </div>
    </div>
  );
}
