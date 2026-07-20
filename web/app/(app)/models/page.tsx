"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { ApiError, api } from "@/lib/api";
import type { ModelArtifact } from "@/lib/types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function ModelsPage() {
  const router = useRouter();
  const [models, setModels] = useState<ModelArtifact[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listModels();
      setModels(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load models");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function download(model: ModelArtifact) {
    setBusyId(model.id);
    try {
      const payload = await api.downloadModel(model.id);
      for (const file of payload.files) {
        window.open(file.url, "_blank", "noopener,noreferrer");
      }
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Download failed");
    } finally {
      setBusyId(null);
    }
  }

  async function deploy(model: ModelArtifact) {
    setBusyId(model.id);
    try {
      const endpoint = await api.deployModel(model.id);
      setError(null);
      if (endpoint.status === "FAILED") {
        setError(endpoint.error_message ?? "Deploy failed");
        return;
      }
      router.push("/endpoints");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Deploy failed");
    } finally {
      setBusyId(null);
    }
  }

  async function remove(model: ModelArtifact) {
    if (!window.confirm(`Delete ${model.name} v${model.version}?`)) {
      return;
    }
    setBusyId(model.id);
    try {
      await api.deleteModel(model.id);
      setModels((prev) => prev.filter((item) => item.id !== model.id));
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Delete failed");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Models</h1>
        <p className="text-sm text-[var(--muted)]">
          Versioned artifacts promoted from successful job outputs
        </p>
      </div>

      {error ? (
        <p className="mb-4 text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}

      {loading && models.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">Loading…</p>
      ) : models.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">No models yet.</p>
      ) : (
        <div className="overflow-x-auto border border-[var(--border)]">
          <table className="w-full text-left text-sm" data-testid="models-table">
            <thead className="border-b border-[var(--border)] bg-[var(--panel)] text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Version</th>
                <th className="px-3 py-2 font-medium">Size</th>
                <th className="px-3 py-2 font-medium">Source job</th>
                <th className="px-3 py-2 font-medium">Created</th>
                <th className="px-3 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {models.map((model) => (
                <tr key={model.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-3 py-2">{model.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">v{model.version}</td>
                  <td className="px-3 py-2 text-[var(--muted)]">
                    {formatBytes(model.size_bytes)}
                  </td>
                  <td className="px-3 py-2">
                    {model.source_job_id ? (
                      <Link
                        href={`/jobs/${model.source_job_id}`}
                        className="font-mono text-xs text-[var(--accent)] hover:underline"
                      >
                        {model.source_job_id.slice(0, 8)}…
                      </Link>
                    ) : (
                      <span className="text-[var(--muted)]">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                    {new Date(model.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => void deploy(model)}
                        disabled={busyId === model.id}
                        className="rounded border border-[var(--accent)] px-2 py-1 text-xs text-[var(--accent)] disabled:opacity-50"
                      >
                        Deploy
                      </button>
                      <button
                        type="button"
                        onClick={() => void download(model)}
                        disabled={busyId === model.id}
                        className="rounded border border-[var(--border)] px-2 py-1 text-xs disabled:opacity-50"
                      >
                        Download
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(model)}
                        disabled={busyId === model.id}
                        className="rounded border border-rose-800 px-2 py-1 text-xs text-rose-300 disabled:opacity-50"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
