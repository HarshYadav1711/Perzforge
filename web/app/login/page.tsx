"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, ready, accessToken, user } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!ready || !accessToken) {
      return;
    }
    router.replace(user?.must_change_password ? "/change-password" : "/jobs");
  }, [accessToken, ready, router, user]);

  if (!ready || accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center text-[var(--muted)]">
        Loading…
      </main>
    );
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Login failed");
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
        <h1 className="text-xl font-semibold tracking-wide text-[var(--accent)]">Perzforge</h1>
        <p className="mt-1 text-sm text-[var(--muted)]">Sign in to the control plane</p>

        <label className="mt-6 flex flex-col gap-1 text-sm">
          <span className="text-[var(--muted)]">Email</span>
          <input
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            data-testid="login-email"
            required
          />
        </label>

        <label className="mt-3 flex flex-col gap-1 text-sm">
          <span className="text-[var(--muted)]">Password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded border border-[var(--border)] bg-[var(--bg)] px-3 py-2"
            data-testid="login-password"
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
          data-testid="login-submit"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
