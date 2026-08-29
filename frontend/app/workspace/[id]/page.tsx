"use client";

import { useEffect, useState, useCallback, use } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/app/lib/supabase-client";
import { apiClient } from "@/app/lib/api-client";

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

export default function WorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: workspaceId } = use(params);
  const router = useRouter();
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [tables, setTables] = useState<CatalogTable[]>([]);
  const [selectedTableId, setSelectedTableId] = useState<string | null>(null);
  const [selectedTable, setSelectedTable] = useState<CatalogTable | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [dragOver, setDragOver] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [filesRes, tablesRes] = await Promise.all([
        apiClient.get<FileRecord[]>(`/workspaces/${workspaceId}/files`),
        apiClient.get<CatalogTable[]>(
          `/workspaces/${workspaceId}/catalog/tables`
        ),
      ]);
      setFiles(filesRes);
      setTables(tablesRes);
      // Auto-select first table if none selected
      if (tablesRes.length > 0 && !selectedTableId) {
        setSelectedTableId(tablesRes[0].id);
      }
    } catch {
      // Silently fail on load
    } finally {
      setLoading(false);
    }
  }, [workspaceId, selectedTableId]);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.replace("/login");
        return;
      }
      loadData();
    });
  }, [router, loadData]);

  // Load table detail when selection changes
  useEffect(() => {
    if (!selectedTableId) return;
    apiClient
      .get<CatalogTable>(
        `/workspaces/${workspaceId}/catalog/tables/${selectedTableId}`
      )
      .then(setSelectedTable)
      .catch(() => setSelectedTable(null));
  }, [workspaceId, selectedTableId]);

  async function handleUpload(file: File) {
    setUploading(true);
    setUploadError(null);
    try {
      await apiClient.uploadFile<FileRecord>(
        `/workspaces/${workspaceId}/files`,
        file
      );
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
    } catch {
      return [];
    }
  }

  const typeColor: Record<string, string> = {
    text: "text-emerald-400",
    integer: "text-blue-400",
    float: "text-cyan-400",
    boolean: "text-amber-400",
    datetime: "text-purple-400",
  };

  return (
    <div className="flex min-h-full flex-col">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-6">
          <button
            onClick={() => router.push("/dashboard")}
            className="flex items-center gap-1.5 text-sm text-text-secondary hover:text-text-primary"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 16 16"
              fill="none"
              className="shrink-0"
            >
              <path
                d="M10 12L6 8l4-4"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            Back
          </button>
          <div className="h-4 w-px bg-border" />
          <h1 className="text-sm font-semibold text-text-primary">
            Workspace
          </h1>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        {/* Upload area */}
        <div
          className={`mb-8 rounded-2xl border-2 border-dashed p-8 text-center transition-colors ${
            dragOver
              ? "border-accent bg-accent-muted"
              : "border-border hover:border-accent/40"
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={handleDrop}
        >
          <div className="mb-3 flex justify-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-muted">
              {uploading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-accent border-t-transparent" />
              ) : (
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                >
                  <path
                    d="M10 14V3m0 0L6 7m4-4l4 4"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-accent"
                  />
                  <path
                    d="M3 14v1a2 2 0 002 2h10a2 2 0 002-2v-1"
                    stroke="currentColor"
                    strokeWidth="1.5"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="text-accent"
                  />
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
              <input
                type="file"
                accept=".csv"
                onChange={handleFileInput}
                className="hidden"
              />
            </label>
          )}
          <p className="mt-2 text-xs text-text-tertiary">
            CSV files up to 5 MB
          </p>
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
            {/* Files list */}
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
                          <svg
                            width="16"
                            height="16"
                            viewBox="0 0 16 16"
                            fill="none"
                          >
                            <path
                              d="M4 1h5.5L13 4.5V13a2 2 0 01-2 2H5a2 2 0 01-2-2V3a2 2 0 012-2z"
                              stroke="currentColor"
                              strokeWidth="1.2"
                              className="text-accent"
                            />
                          </svg>
                        </div>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-text-primary">
                            {f.filename}
                          </p>
                          <p className="text-xs text-text-tertiary">
                            {formatBytes(f.size_bytes)}
                            {f.row_count != null && ` · ${f.row_count.toLocaleString()} rows`}
                          </p>
                        </div>
                        <span
                          className={`shrink-0 rounded-full px-2.5 py-0.5 text-xs font-medium ${
                            f.state === "READY"
                              ? "bg-success/15 text-success"
                              : f.state === "FAILED"
                                ? "bg-error/15 text-error"
                                : "bg-warning/15 text-warning"
                          }`}
                        >
                          {f.state}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Schema preview */}
            {selectedTable && (
              <div>
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-text-tertiary">
                  Schema Preview —{" "}
                  <span className="normal-case text-text-primary">
                    {selectedTable.name}
                  </span>
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
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                          Column
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                          Type
                        </th>
                        <th className="px-4 py-3 text-center text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                          Nullable
                        </th>
                        <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-text-tertiary">
                          Sample Values
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedTable.columns.map((col, i) => {
                        const samples = parseSamples(col.sample_values);
                        return (
                          <tr
                            key={col.id}
                            className={
                              i % 2 === 0
                                ? "bg-background"
                                : "bg-surface/30"
                            }
                          >
                            <td className="px-4 py-3 font-mono text-xs text-text-primary">
                              {col.name}
                            </td>
                            <td className="px-4 py-3">
                              <span
                                className={`inline-block rounded-md bg-surface px-2 py-0.5 font-mono text-xs ${typeColor[col.data_type] ?? "text-text-secondary"}`}
                              >
                                {col.data_type}
                              </span>
                            </td>
                            <td className="px-4 py-3 text-center">
                              {col.nullable ? (
                                <span className="text-xs text-warning">yes</span>
                              ) : (
                                <span className="text-xs text-text-tertiary">
                                  no
                                </span>
                              )}
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex flex-wrap gap-1.5">
                                {samples.slice(0, 4).map((v, j) => (
                                  <span
                                    key={j}
                                    className="inline-block max-w-[140px] truncate rounded bg-surface px-2 py-0.5 font-mono text-xs text-text-secondary"
                                  >
                                    {v}
                                  </span>
                                ))}
                                {samples.length > 4 && (
                                  <span className="text-xs text-text-tertiary">
                                    +{samples.length - 4}
                                  </span>
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
          </>
        )}
      </main>
    </div>
  );
}
