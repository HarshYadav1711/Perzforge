"use client";

import { useCallback, useEffect, useState } from "react";

import { EndpointStatusChip } from "@/components/StatusChip";
import { ApiError, api } from "@/lib/api";
import type { Endpoint } from "@/lib/types";

const DEFAULT_PAYLOAD = '{\n  "input": "hello"\n}';

export default function EndpointsPage() {
  const [endpoints, setEndpoints] = useState<Endpoint[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [tryRoute, setTryRoute] = useState<string | null>(null);
  const [payloadText, setPayloadText] = useState(DEFAULT_PAYLOAD);
  const [predictResult, setPredictResult] = useState<string | null>(null);
  const [predictError, setPredictError] = useState<string | null>(null);
  const [predicting, setPredicting] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.listEndpoints();
      setEndpoints(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load endpoints");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [load]);

  async function stop(endpoint: Endpoint) {
    if (!window.confirm(`Stop endpoint ${endpoint.route}?`)) {
      return;
    }
    setBusyId(endpoint.id);
    try {
      await api.stopEndpoint(endpoint.id);
      await load();
      setError(null);
      if (tryRoute === endpoint.route) {
        setTryRoute(null);
        setPredictResult(null);
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Stop failed");
    } finally {
      setBusyId(null);
    }
  }

  function openTry(endpoint: Endpoint) {
    setTryRoute(endpoint.route);
    setPayloadText(DEFAULT_PAYLOAD);
    setPredictResult(null);
    setPredictError(null);
  }

  async function runPredict() {
    if (!tryRoute) {
      return;
    }
    let parsed: Record<string, unknown>;
    try {
      parsed = JSON.parse(payloadText) as Record<string, unknown>;
      if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") {
        throw new Error("payload must be a JSON object");
      }
    } catch (err) {
      setPredictError(err instanceof Error ? err.message : "Invalid JSON");
      setPredictResult(null);
      return;
    }

    setPredicting(true);
    setPredictError(null);
    try {
      const result = await api.predictEndpoint(tryRoute, parsed);
      setPredictResult(JSON.stringify(result, null, 2));
    } catch (err) {
      setPredictError(err instanceof ApiError ? err.detail : "Predict failed");
      setPredictResult(null);
    } finally {
      setPredicting(false);
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-semibold">Endpoints</h1>
        <p className="text-sm text-[var(--muted)]">
          Deployed model inference routes · auto-refreshes every 5 seconds
        </p>
      </div>

      {error ? (
        <p className="mb-4 text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}

      {loading && endpoints.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">Loading…</p>
      ) : endpoints.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">
          No endpoints yet. Deploy a model from the Models page.
        </p>
      ) : (
        <div className="overflow-x-auto border border-[var(--border)]">
          <table className="w-full text-left text-sm" data-testid="endpoints-table">
            <thead className="border-b border-[var(--border)] bg-[var(--panel)] text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Route</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Created</th>
                <th className="px-3 py-2 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {endpoints.map((endpoint) => (
                <tr key={endpoint.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-3 py-2">{endpoint.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{endpoint.route}</td>
                  <td className="px-3 py-2">
                    <EndpointStatusChip status={endpoint.status} />
                    {endpoint.error_message ? (
                      <p className="mt-1 max-w-xs truncate text-xs text-rose-400">
                        {endpoint.error_message}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                    {new Date(endpoint.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex gap-2">
                      {endpoint.status === "LIVE" ? (
                        <button
                          type="button"
                          onClick={() => openTry(endpoint)}
                          className="rounded border border-[var(--border)] px-2 py-1 text-xs"
                        >
                          Try it
                        </button>
                      ) : null}
                      {endpoint.status === "LIVE" || endpoint.status === "STARTING" ? (
                        <button
                          type="button"
                          onClick={() => void stop(endpoint)}
                          disabled={busyId === endpoint.id}
                          className="rounded border border-rose-800 px-2 py-1 text-xs text-rose-300 disabled:opacity-50"
                        >
                          Stop
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tryRoute ? (
        <div className="mt-8 border border-[var(--border)] p-4" data-testid="predict-console">
          <div className="mb-3 flex items-baseline justify-between gap-4">
            <h2 className="text-sm font-semibold">
              Try it · <span className="font-mono text-[var(--accent)]">{tryRoute}</span>
            </h2>
            <button
              type="button"
              onClick={() => setTryRoute(null)}
              className="text-xs text-[var(--muted)] hover:text-[var(--fg)]"
            >
              Close
            </button>
          </div>
          <label className="mb-1 block text-xs text-[var(--muted)]" htmlFor="predict-payload">
            JSON body
          </label>
          <textarea
            id="predict-payload"
            value={payloadText}
            onChange={(e) => setPayloadText(e.target.value)}
            rows={8}
            className="mb-3 w-full border border-[var(--border)] bg-[var(--bg)] p-2 font-mono text-xs"
            spellCheck={false}
          />
          <button
            type="button"
            onClick={() => void runPredict()}
            disabled={predicting}
            className="rounded bg-[var(--accent)] px-3 py-2 text-sm font-medium text-black disabled:opacity-50"
          >
            {predicting ? "Running…" : "Predict"}
          </button>
          {predictError ? (
            <p className="mt-3 text-sm text-rose-400" role="alert">
              {predictError}
            </p>
          ) : null}
          {predictResult ? (
            <pre className="mt-3 overflow-x-auto border border-[var(--border)] bg-[var(--panel)] p-3 font-mono text-xs">
              {predictResult}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
