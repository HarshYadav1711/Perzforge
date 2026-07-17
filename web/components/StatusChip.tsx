import type { JobStatus } from "@/lib/types";

const STYLES: Record<JobStatus, string> = {
  QUEUED: "bg-slate-700 text-slate-200",
  RUNNING: "bg-sky-900 text-sky-200",
  CANCELLING: "bg-amber-900 text-amber-200",
  SUCCEEDED: "bg-emerald-900 text-emerald-200",
  FAILED: "bg-rose-900 text-rose-200",
  CANCELLED: "bg-zinc-700 text-zinc-300",
};

export function StatusChip({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 font-mono text-xs tracking-wide ${STYLES[status] ?? STYLES.QUEUED}`}
    >
      {status}
    </span>
  );
}
