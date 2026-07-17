"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { jobLogsWsUrl } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type ConnState = "connecting" | "live" | "reconnecting" | "closed" | "paused";

interface LogViewerProps {
  jobId: string;
  finished?: boolean;
}

export function LogViewer({ jobId, finished = false }: LogViewerProps) {
  const { accessToken } = useAuth();
  const [lines, setLines] = useState<string[]>([]);
  const [paused, setPaused] = useState(false);
  const [conn, setConn] = useState<ConnState>("connecting");
  const bottomRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const pausedRef = useRef(false);
  const bufferRef = useRef<string[]>([]);

  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  useEffect(() => {
    if (!accessToken) {
      return;
    }

    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const connect = () => {
      if (cancelled) {
        return;
      }
      setConn(attempt === 0 ? "connecting" : "reconnecting");
      const ws = new WebSocket(jobLogsWsUrl(jobId, accessToken));
      wsRef.current = ws;

      ws.onopen = () => {
        attempt = 0;
        setConn(pausedRef.current ? "paused" : "live");
      };

      ws.onmessage = (event) => {
        const text = String(event.data);
        if (pausedRef.current) {
          bufferRef.current.push(text);
          return;
        }
        setLines((prev) => [...prev, text]);
      };

      ws.onerror = () => {
        ws.close();
      };

      ws.onclose = () => {
        if (cancelled) {
          return;
        }
        if (finished) {
          setConn("closed");
          return;
        }
        setConn("reconnecting");
        attempt += 1;
        const delay = Math.min(8000, 500 * 2 ** Math.min(attempt, 4));
        retryTimer = setTimeout(connect, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (retryTimer) {
        clearTimeout(retryTimer);
      }
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [accessToken, jobId, finished]);

  useEffect(() => {
    if (!paused) {
      if (bufferRef.current.length) {
        const pending = bufferRef.current;
        bufferRef.current = [];
        setLines((prev) => [...prev, ...pending]);
      }
      setConn((c) => (c === "paused" ? "live" : c));
    } else {
      setConn((c) => (c === "live" ? "paused" : c));
    }
  }, [paused]);

  useEffect(() => {
    if (!paused) {
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [lines, paused]);

  const indicator = useMemo(() => {
    switch (conn) {
      case "live":
        return "Live";
      case "connecting":
        return "Connecting…";
      case "reconnecting":
        return "Reconnecting…";
      case "paused":
        return "Paused";
      default:
        return "Closed";
    }
  }, [conn]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-2 flex items-center justify-between gap-3">
        <div className="text-xs text-[var(--muted)]">
          Logs · <span className="text-[var(--fg)]">{indicator}</span>
        </div>
        <button
          type="button"
          onClick={() => setPaused((p) => !p)}
          className="rounded border border-[var(--border)] px-2 py-1 text-xs text-[var(--muted)] hover:text-[var(--fg)]"
        >
          {paused ? "Resume" : "Pause"}
        </button>
      </div>
      <pre className="min-h-[320px] flex-1 overflow-auto rounded border border-[var(--border)] bg-black/40 p-3 font-mono text-xs leading-5 text-[var(--fg)]">
        {lines.length === 0 ? (
          <span className="text-[var(--muted)]">Waiting for log lines…</span>
        ) : (
          lines.map((line, i) => (
            <div key={`${i}-${line.slice(0, 24)}`}>{line}</div>
          ))
        )}
        <div ref={bottomRef} />
      </pre>
    </div>
  );
}
