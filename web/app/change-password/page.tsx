"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError, api } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function ChangePasswordPage() {
  const { accessToken, ready, refreshUser, logout } = useAuth();
  const router = useRouter();
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center text-[var(--muted)]">
        Loading…
      </main>
    );
  }

  if (!accessToken) {
    router.replace("/login");
    return null;
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (newPassword.length < 12) {
      setError("New password must be at least 12 characters");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.changePassword(oldPassword, newPassword);
      await refreshUser();
      router.replace("/jobs");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Password change failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={(e) => void onSubmit(e)}
        className="w-full max-w-sm border border-[var(--border)] bg-[var(--panel)] p-6"
      >
        <h1 className="text-lg font-semibold">Change password</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">
          A temporary password was issued. Set a new one to continue.
        </p>

        <label className="mt-6 flex flex-col gap-1 text-sm">
          <span className="text-[var(--muted)]">Current password</span>
          <input
            type="password"
            value={oldPassword}
            onChange={(e) => setOldPassword(e.target.value)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            required
          />
        </label>

        <label className="mt-3 flex flex-col gap-1 text-sm">
          <span className="text-[var(--muted)]">New password (min 12)</span>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            minLength={12}
            required
          />
        </label>

        {error ? (
          <p className="mt-3 text-sm text-rose-400" role="alert">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={busy}
          className="mt-5 w-full rounded bg-[var(--accent)] py-2 text-sm font-medium text-black disabled:opacity-50"
        >
          {busy ? "Saving…" : "Update password"}
        </button>
        <button
          type="button"
          onClick={() => void logout()}
          className="mt-2 w-full py-2 text-sm text-[var(--muted)]"
        >
          Sign out
        </button>
      </form>
    </main>
  );
}
