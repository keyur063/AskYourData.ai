"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/app/lib/supabase-client";
import { apiClient } from "@/app/lib/api-client";

interface KeyStatus {
  configured: boolean;
  model: string | null;
}

export default function SettingsPage() {
  const router = useRouter();
  const [status, setStatus] = useState<KeyStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [removing, setRemoving] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      if (!session) {
        router.replace("/login");
        return;
      }
      loadStatus();
    });
  }, [router]);

  async function loadStatus() {
    try {
      const data = await apiClient.get<KeyStatus>("/me/groq-key");
      setStatus(data);
      if (data.model) setModel(data.model);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load key status");
    } finally {
      setLoading(false);
    }
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!apiKey.trim()) return;
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const data = await apiClient.post<KeyStatus>("/me/groq-key", {
        api_key: apiKey.trim(),
        model: model.trim() || null,
      });
      setStatus(data);
      setApiKey("");
      setSuccess("API key saved successfully.");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save key");
    } finally {
      setSaving(false);
    }
  }

  async function handleRemove() {
    if (!confirm("Remove your Groq API key? You won't be able to query until you add a new one.")) return;
    setRemoving(true);
    setError(null);
    setSuccess(null);
    try {
      await apiClient.delete("/me/groq-key");
      setStatus({ configured: false, model: null });
      setModel("");
      setSuccess("API key removed.");
      setTimeout(() => setSuccess(null), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to remove key");
    } finally {
      setRemoving(false);
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      {/* Header */}
      <header className="border-b border-border bg-surface/50 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-3xl items-center justify-between px-6">
          <button
            onClick={() => router.push("/dashboard")}
            className="text-lg font-bold tracking-tight hover:opacity-80"
          >
            Ask<span className="text-accent">YourData</span>
          </button>
          <nav className="flex items-center gap-4">
            <button
              onClick={() => router.push("/dashboard")}
              className="rounded-lg px-3 py-1.5 text-xs text-text-secondary hover:bg-surface-hover hover:text-text-primary"
            >
              ← Dashboard
            </button>
          </nav>
        </div>
      </header>

      {/* Main */}
      <main className="mx-auto w-full max-w-3xl flex-1 px-6 py-10">
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-text-primary">Settings</h2>
          <p className="mt-1 text-sm text-text-secondary">
            Manage your Groq API key for AI-powered queries
          </p>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          </div>
        ) : (
          <div className="space-y-6">
            {/* Status Card */}
            <div className="rounded-xl border border-border bg-surface p-6">
              <div className="mb-4 flex items-center gap-3">
                <div
                  className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                    status?.configured ? "bg-success/15" : "bg-warning/15"
                  }`}
                >
                  {status?.configured ? (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path
                        d="M6 10l3 3 5-6"
                        stroke="var(--success)"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  ) : (
                    <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                      <path
                        d="M10 6v4m0 4h.01"
                        stroke="var(--warning)"
                        strokeWidth="2"
                        strokeLinecap="round"
                      />
                    </svg>
                  )}
                </div>
                <div>
                  <h3 className="font-semibold text-text-primary">
                    Groq API Key
                  </h3>
                  <p className="text-sm text-text-secondary">
                    {status?.configured ? (
                      <>
                        <span className="text-success">Key configured ✓</span>
                        {status.model && (
                          <span className="ml-2 text-text-tertiary">
                            Model: {status.model}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-warning">No key set — add one to start querying</span>
                    )}
                  </p>
                </div>
              </div>

              {status?.configured && (
                <button
                  onClick={handleRemove}
                  disabled={removing}
                  className="rounded-lg border border-error/30 px-4 py-2 text-sm text-error hover:bg-error/10 disabled:opacity-50"
                >
                  {removing ? "Removing..." : "Remove key"}
                </button>
              )}
            </div>

            {/* Set / Update form */}
            <form
              onSubmit={handleSave}
              className="rounded-xl border border-border bg-surface p-6"
            >
              <h3 className="mb-4 font-semibold text-text-primary">
                {status?.configured ? "Update API Key" : "Add API Key"}
              </h3>
              <div className="space-y-4">
                <div>
                  <label
                    htmlFor="apiKeyInput"
                    className="mb-1.5 block text-sm font-medium text-text-secondary"
                  >
                    Groq API Key
                  </label>
                  <input
                    id="apiKeyInput"
                    type="password"
                    required
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="gsk_..."
                    className="w-full rounded-lg border border-border bg-background px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                    autoComplete="off"
                  />
                  <p className="mt-1.5 text-xs text-text-tertiary">
                    Get your key from{" "}
                    <a
                      href="https://console.groq.com/keys"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      console.groq.com/keys
                    </a>
                    . Your key is encrypted before storage and never displayed.
                  </p>
                </div>
                <div>
                  <label
                    htmlFor="modelInput"
                    className="mb-1.5 block text-sm font-medium text-text-secondary"
                  >
                    Model override{" "}
                    <span className="font-normal text-text-tertiary">(optional)</span>
                  </label>
                  <input
                    id="modelInput"
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="llama-3.3-70b-versatile"
                    className="w-full rounded-lg border border-border bg-background px-3.5 py-2.5 text-sm text-text-primary placeholder:text-text-tertiary focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
                  />
                  <p className="mt-1.5 text-xs text-text-tertiary">
                    Leave empty for the default model. See{" "}
                    <a
                      href="https://console.groq.com/docs/models"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent hover:underline"
                    >
                      Groq docs
                    </a>{" "}
                    for available models.
                  </p>
                </div>
                <button
                  type="submit"
                  disabled={saving || !apiKey.trim()}
                  className="rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white hover:bg-accent-hover disabled:opacity-50"
                >
                  {saving ? "Saving..." : status?.configured ? "Update key" : "Save key"}
                </button>
              </div>
            </form>

            {/* Messages */}
            {error && (
              <div className="rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
                {error}
              </div>
            )}
            {success && (
              <div className="rounded-lg border border-success/30 bg-success/10 px-4 py-3 text-sm text-success">
                {success}
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
