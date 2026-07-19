"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { LogViewer } from "@/components/LogViewer";
import { StatusChip } from "@/components/StatusChip";
import { ApiError, api } from "@/lib/api";
import type { Job, JobStatus } from "@/lib/types";

const TERMINAL: JobStatus[] = ["SUCCEEDED", "FAILED", "CANCELLED"];
const CANCELLABLE: JobStatus[] = ["QUEUED", "RUNNING"];

export default function JobDetailPage() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.getJob(jobId);
      setJob(data);
      setError(null);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Failed to load job");
    }
  }, [jobId]);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 5000);
    return () => clearInterval(id);
  }, [load]);

  async function cancel() {
    setCancelling(true);
    try {
      const updated = await api.cancelJob(jobId);
      setJob(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Cancel failed");
    } finally {
      setCancelling(false);
    }
  }

  if (error && !job) {
    return (
      <p className="text-sm text-rose-400" role="alert">
        {error}
      </p>
    );
  }

  if (!job) {
    return <p className="text-sm text-[var(--muted)]">Loading…</p>;
  }

  const finished = TERMINAL.includes(job.status);

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{job.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-[var(--muted)]">
            <StatusChip status={job.status} />
            <span className="font-mono text-xs">{job.id}</span>
          </div>
        </div>
        {CANCELLABLE.includes(job.status) ? (
          <button
            type="button"
            onClick={() => void cancel()}
            disabled={cancelling}
            className="rounded border border-rose-700 px-3 py-2 text-sm text-rose-300 disabled:opacity-50"
          >
            {cancelling ? "Cancelling…" : "Cancel job"}
          </button>
        ) : null}
      </div>

      {error ? (
        <p className="text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}

      <dl className="grid max-w-2xl grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt className="text-[var(--muted)]">Image</dt>
        <dd className="font-mono text-xs">{job.spec.image}</dd>
        <dt className="text-[var(--muted)]">Command</dt>
        <dd className="font-mono text-xs">{JSON.stringify(job.spec.command)}</dd>
        <dt className="text-[var(--muted)]">GPU</dt>
        <dd>{job.spec.gpu ? "yes" : "no"}</dd>
        {job.mlflow_run_id ? (
          <>
            <dt className="text-[var(--muted)]">MLflow</dt>
            <dd>
              <a
                href={`${(process.env.NEXT_PUBLIC_MLFLOW_URL ?? "http://127.0.0.1:5000").replace(/\/$/, "")}/#/runs/${job.mlflow_run_id}`}
                target="_blank"
                rel="noreferrer"
                className="text-[var(--accent)] hover:underline"
              >
                Open run {job.mlflow_run_id.slice(0, 8)}…
              </a>
            </dd>
          </>
        ) : null}
        {job.artifact_error ? (
          <>
            <dt className="text-[var(--muted)]">Artifacts</dt>
            <dd className="text-amber-300">{job.artifact_error}</dd>
          </>
        ) : null}
        {job.error_message ? (
          <>
            <dt className="text-[var(--muted)]">Error</dt>
            <dd className="text-rose-300">{job.error_message}</dd>
          </>
        ) : null}
      </dl>

      <LogViewer jobId={job.id} finished={finished} />
    </div>
  );
}
