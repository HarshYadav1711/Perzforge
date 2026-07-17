"use client";

import { useEffect, useState } from "react";

import { QuotaBar } from "@/components/QuotaBar";
import { ApiError, api } from "@/lib/api";
import type { MeQuota } from "@/lib/types";

export default function QuotaPage() {
  const [quota, setQuota] = useState<MeQuota | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        setQuota(await api.getQuota());
      } catch (err) {
        setError(err instanceof ApiError ? err.detail : "Failed to load quota");
      }
    })();
  }, []);

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold">My quota</h1>
      <p className="mb-6 text-sm text-[var(--muted)]">Current usage against your account limits</p>

      {error ? (
        <p className="text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}

      {!quota && !error ? (
        <p className="text-sm text-[var(--muted)]">Loading…</p>
      ) : null}

      {quota ? (
        <div className="flex max-w-md flex-col gap-5">
          {Object.entries(quota.usage).map(([name, entry]) => (
            <QuotaBar key={name} name={name} entry={entry} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
