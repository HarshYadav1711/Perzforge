import type { EndpointStatus, JobStatus } from "@/lib/types";

const JOB_STYLES: Record<JobStatus, string> = {
  QUEUED: "bg-slate-700 text-slate-200",
  RUNNING: "bg-sky-900 text-sky-200",
  CANCELLING: "bg-amber-900 text-amber-200",
  SUCCEEDED: "bg-emerald-900 text-emerald-200",
  FAILED: "bg-rose-900 text-rose-200",
  CANCELLED: "bg-zinc-700 text-zinc-300",
};

const ENDPOINT_STYLES: Record<EndpointStatus, string> = {
  STARTING: "bg-amber-900 text-amber-200",
  LIVE: "bg-emerald-900 text-emerald-200",
  STOPPED: "bg-zinc-700 text-zinc-300",
  FAILED: "bg-rose-900 text-rose-200",
};

export function StatusChip({ status }: { status: JobStatus }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 font-mono text-xs tracking-wide ${JOB_STYLES[status] ?? JOB_STYLES.QUEUED}`}
    >
      {status}
    </span>
  );
}

export function EndpointStatusChip({ status }: { status: EndpointStatus }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 font-mono text-xs tracking-wide ${ENDPOINT_STYLES[status] ?? ENDPOINT_STYLES.STARTING}`}
    >
      {status}
    </span>
  );
}
