"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { JobForm } from "@/components/JobForm";
import { ApiError, api } from "@/lib/api";
import type { SubmitJobPayload } from "@/lib/types";

export default function NewJobPage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(payload: SubmitJobPayload) {
    setSubmitting(true);
    setError(null);
    try {
      const job = await api.submitJob(payload);
      router.push(`/jobs/${job.id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <h1 className="mb-1 text-xl font-semibold">New job</h1>
      <p className="mb-6 text-sm text-[var(--muted)]">
        Image must match the platform allow-list. Command is argv only — no shell strings.
      </p>
      {error ? (
        <p className="mb-4 text-sm text-rose-400" role="alert">
          {error}
        </p>
      ) : null}
      <JobForm onSubmit={onSubmit} submitting={submitting} />
    </div>
  );
}
