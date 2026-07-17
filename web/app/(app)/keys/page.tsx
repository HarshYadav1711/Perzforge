"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";

import { KeyRevealModal } from "@/components/KeyRevealModal";
import { ApiError, api } from "@/lib/api";
import { API_KEY_SCOPES, type ApiKey } from "@/lib/types";

export default function KeysPage() {
  const [keys, setKeys] = useState<ApiKey[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [scopes, setScopes] = useState<string[]>(["jobs:read"]);
  const [revealed, setRevealed] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setKeys(await api.listKeys());
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load keys");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function toggleScope(scope: string) {
    setScopes((prev) =>
      prev.includes(scope) ? prev.filter((s) => s !== scope) : [...prev, scope],
    );
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (!name.trim() || scopes.length === 0) {
      setError("Name and at least one scope are required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const created = await api.createKey({ name: name.trim(), scopes });
      setRevealed(created.store_this_now);
      setName("");
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function revoke(id: string) {
    try {
      await api.deleteKey(id);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Delete failed");
    }
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold">API Keys</h1>
      <p className="mb-6 text-sm text-[var(--muted)]">
        Keys are shown once at creation. Hashes are stored server-side only.
      </p>

      {error ? (
        <p className="mb-4 text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}

      <form
        onSubmit={(e) => void onCreate(e)}
        className="mb-8 max-w-lg border border-[var(--border)] bg-[var(--panel)] p-4"
      >
        <h2 className="mb-3 text-sm font-medium">Create key</h2>
        <label className="flex flex-col gap-1 text-sm">
          <span className="text-[var(--muted)]">Name</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            data-testid="key-name"
          />
        </label>
        <fieldset className="mt-3">
          <legend className="text-sm text-[var(--muted)]">Scopes</legend>
          <div className="mt-2 flex flex-wrap gap-3">
            {API_KEY_SCOPES.map((scope) => (
              <label key={scope} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={scopes.includes(scope)}
                  onChange={() => toggleScope(scope)}
                />
                <span className="font-mono text-xs">{scope}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <button
          type="submit"
          disabled={busy}
          className="mt-4 rounded bg-[var(--accent)] px-3 py-2 text-sm font-medium text-black disabled:opacity-50"
          data-testid="key-create"
        >
          {busy ? "Creating…" : "Create"}
        </button>
      </form>

      <div className="overflow-x-auto border border-[var(--border)]">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-[var(--border)] bg-[var(--panel)] text-[var(--muted)]">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Prefix</th>
              <th className="px-3 py-2 font-medium">Scopes</th>
              <th className="px-3 py-2 font-medium">Created</th>
              <th className="px-3 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {keys.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-[var(--muted)]">
                  No keys yet.
                </td>
              </tr>
            ) : (
              keys.map((key) => (
                <tr key={key.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-3 py-2">{key.name}</td>
                  <td className="px-3 py-2 font-mono text-xs">{key.prefix}…</td>
                  <td className="px-3 py-2 font-mono text-xs">{key.scopes.join(", ")}</td>
                  <td className="px-3 py-2 text-xs text-[var(--muted)]">
                    {new Date(key.created_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {!key.revoked ? (
                      <button
                        type="button"
                        onClick={() => void revoke(key.id)}
                        className="text-xs text-rose-300"
                      >
                        Revoke
                      </button>
                    ) : (
                      <span className="text-xs text-[var(--muted)]">revoked</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {revealed ? (
        <KeyRevealModal plaintextKey={revealed} onClose={() => setRevealed(null)} />
      ) : null}
    </div>
  );
}
