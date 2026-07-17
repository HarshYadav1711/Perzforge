import type { QuotaUsageEntry } from "@/lib/types";

const LABELS: Record<string, string> = {
  max_concurrent_jobs: "Concurrent jobs",
  max_jobs_per_day: "Jobs per day",
  max_storage_mb: "Storage (MB)",
  max_instances: "Instances",
  max_llm_tokens_per_day: "LLM tokens / day",
};

export function QuotaBar({ name, entry }: { name: string; entry: QuotaUsageEntry }) {
  const pct =
    entry.limit <= 0 ? 0 : Math.min(100, Math.round((entry.current / entry.limit) * 100));
  return (
    <div className="flex flex-col gap-1" data-testid={`quota-${name}`}>
      <div className="flex justify-between text-sm">
        <span>{LABELS[name] ?? name}</span>
        <span className="font-mono text-[var(--muted)]">
          {entry.current} / {entry.limit}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded bg-[var(--panel-hover)]">
        <div
          className="h-full bg-[var(--accent)] transition-all"
          style={{ width: `${pct}%` }}
          role="progressbar"
          aria-valuenow={entry.current}
          aria-valuemin={0}
          aria-valuemax={entry.limit}
        />
      </div>
    </div>
  );
}
