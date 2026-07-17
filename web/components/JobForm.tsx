"use client";

import { FormEvent, useState } from "react";

import { ALLOWED_IMAGES, type JobSpec, type SubmitJobPayload } from "@/lib/types";

export interface JobFormProps {
  onSubmit: (payload: SubmitJobPayload) => Promise<void> | void;
  submitting?: boolean;
}

export function validateJobForm(values: {
  name: string;
  image: string;
  commandParts: string[];
  gpu: boolean;
  timeout_minutes: number;
}): { ok: true; payload: SubmitJobPayload } | { ok: false; error: string } {
  const name = values.name.trim();
  if (!name) {
    return { ok: false, error: "Name is required" };
  }
  const command = values.commandParts.map((p) => p.trim()).filter(Boolean);
  if (command.length === 0) {
    return { ok: false, error: "Command must have at least one argument" };
  }
  if (!values.image) {
    return { ok: false, error: "Image is required" };
  }
  if (values.timeout_minutes < 1 || values.timeout_minutes > 720) {
    return { ok: false, error: "Timeout must be between 1 and 720 minutes" };
  }
  const spec: JobSpec = {
    image: values.image,
    command,
    env: {},
    gpu: values.gpu,
    timeout_minutes: values.timeout_minutes,
  };
  return { ok: true, payload: { name, spec } };
}

export function JobForm({ onSubmit, submitting = false }: JobFormProps) {
  const [name, setName] = useState("");
  const [image, setImage] = useState<string>(ALLOWED_IMAGES[0]);
  const [commandParts, setCommandParts] = useState<string[]>(["python", "-c", "print('hello')"]);
  const [gpu, setGpu] = useState(false);
  const [timeoutMinutes, setTimeoutMinutes] = useState(60);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const result = validateJobForm({
      name,
      image,
      commandParts,
      gpu,
      timeout_minutes: timeoutMinutes,
    });
    if (!result.ok) {
      setError(result.error);
      return;
    }
    setError(null);
    await onSubmit(result.payload);
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="flex max-w-xl flex-col gap-4">
      <label className="flex flex-col gap-1 text-sm">
        <span className="text-[var(--muted)]">Name</span>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2"
          data-testid="job-name"
        />
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-[var(--muted)]">Image</span>
        <select
          value={image}
          onChange={(e) => setImage(e.target.value)}
          className="rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2"
          data-testid="job-image"
        >
          {ALLOWED_IMAGES.map((img) => (
            <option key={img} value={img}>
              {img}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm text-[var(--muted)]">Command (argv)</legend>
        {commandParts.map((part, index) => (
          <div key={index} className="flex gap-2">
            <input
              value={part}
              onChange={(e) => {
                const next = [...commandParts];
                next[index] = e.target.value;
                setCommandParts(next);
              }}
              className="flex-1 rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2 font-mono text-sm"
              data-testid={`job-cmd-${index}`}
            />
            <button
              type="button"
              className="rounded border border-[var(--border)] px-2 text-xs text-[var(--muted)]"
              onClick={() => setCommandParts(commandParts.filter((_, i) => i !== index))}
              aria-label={`Remove argument ${index + 1}`}
            >
              Remove
            </button>
          </div>
        ))}
        <button
          type="button"
          className="self-start text-xs text-[var(--accent)]"
          onClick={() => setCommandParts([...commandParts, ""])}
        >
          + Add argument
        </button>
      </fieldset>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={gpu}
          onChange={(e) => setGpu(e.target.checked)}
          data-testid="job-gpu"
        />
        <span>Request GPU</span>
      </label>

      <label className="flex flex-col gap-1 text-sm">
        <span className="text-[var(--muted)]">Timeout (minutes)</span>
        <input
          type="number"
          min={1}
          max={720}
          value={timeoutMinutes}
          onChange={(e) => setTimeoutMinutes(Number(e.target.value))}
          className="w-32 rounded border border-[var(--border)] bg-[var(--panel)] px-3 py-2"
        />
      </label>

      {error ? (
        <p className="text-sm text-rose-400" role="alert" data-testid="job-form-error">
          {error}
        </p>
      ) : null}

      <button
        type="submit"
        disabled={submitting}
        className="rounded bg-[var(--accent)] px-4 py-2 text-sm font-medium text-black disabled:opacity-50"
        data-testid="job-submit"
      >
        {submitting ? "Submitting…" : "Submit job"}
      </button>
    </form>
  );
}
