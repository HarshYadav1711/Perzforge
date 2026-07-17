"use client";

import { useAuth } from "@/lib/auth";
import { Sidebar } from "@/components/Sidebar";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { ready, accessToken } = useAuth();

  if (!ready) {
    return (
      <main className="flex min-h-screen items-center justify-center text-[var(--muted)]">
        Loading…
      </main>
    );
  }

  if (!accessToken) {
    return (
      <main className="flex min-h-screen items-center justify-center text-[var(--muted)]">
        Redirecting…
      </main>
    );
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <main className="flex min-h-screen min-w-0 flex-1 flex-col p-6">{children}</main>
    </div>
  );
}
