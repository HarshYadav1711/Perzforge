"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { StatusChip } from "@/components/StatusChip";
import { ApiError, api } from "@/lib/api";
import type { Job } from "@/lib/types";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await api.listJobs();
      setJobs(data.items);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [load]);

  return (
    <div>
      <div className="mb-6 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">Jobs</h1>
          <p className="text-sm text-[var(--muted)]">Auto-refreshes every 5 seconds</p>
        </div>
        <Link
          href="/jobs/new"
          className="rounded bg-[var(--accent)] px-3 py-2 text-sm font-medium text-black"
        >
          New job
        </Link>
      </div>

      {error ? (
        <p className="mb-4 text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}

      {loading && jobs.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">Loading…</p>
      ) : jobs.length === 0 ? (
        <p className="text-sm text-[var(--muted)]">No jobs yet.</p>
      ) : (
        <div className="overflow-x-auto border border-[var(--border)]">
          <table className="w-full text-left text-sm" data-testid="jobs-table">
            <thead className="border-b border-[var(--border)] bg-[var(--panel)] text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2 font-medium">Name</th>
                <th className="px-3 py-2 font-medium">Status</th>
                <th className="px-3 py-2 font-medium">Queued</th>
                <th className="px-3 py-2 font-medium">Image</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="border-b border-[var(--border)] last:border-0">
                  <td className="px-3 py-2">
                    <Link
                      href={`/jobs/${job.id}`}
                      className="text-[var(--accent)] hover:underline"
                      data-testid={`job-row-${job.name}`}
                    >
                      {job.name}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <StatusChip status={job.status} />
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                    {new Date(job.queued_at).toLocaleString()}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                    {job.spec.image}
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
