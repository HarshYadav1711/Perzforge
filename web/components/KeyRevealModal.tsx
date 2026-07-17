"use client";

import { useState } from "react";

interface KeyRevealModalProps {
  plaintextKey: string;
  onClose: () => void;
}

export function KeyRevealModal({ plaintextKey, onClose }: KeyRevealModalProps) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(plaintextKey);
    setCopied(true);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      role="dialog"
      aria-modal="true"
      aria-labelledby="key-reveal-title"
      data-testid="key-reveal-modal"
    >
      <div className="w-full max-w-lg rounded border border-[var(--border)] bg-[var(--panel)] p-5 shadow-xl">
        <h2 id="key-reveal-title" className="text-lg font-semibold">
          Store this API key now
        </h2>
        <p className="mt-2 text-sm text-amber-300" data-testid="key-reveal-warning">
          You won&apos;t see this again. Copy it before closing.
        </p>
        <pre
          className="mt-4 overflow-x-auto rounded border border-[var(--border)] bg-black/40 p-3 font-mono text-sm"
          data-testid="key-reveal-value"
        >
          {plaintextKey}
        </pre>
        <div className="mt-4 flex gap-2">
          <button
            type="button"
            onClick={() => void copy()}
            className="rounded bg-[var(--accent)] px-3 py-2 text-sm font-medium text-black"
            data-testid="key-reveal-copy"
          >
            {copied ? "Copied" : "Copy"}
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-[var(--border)] px-3 py-2 text-sm text-[var(--muted)]"
            data-testid="key-reveal-close"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
}
