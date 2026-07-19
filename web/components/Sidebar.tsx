"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";

const NAV = [
  { href: "/jobs", label: "Jobs" },
  { href: "/jobs/new", label: "New Job" },
  { href: "/models", label: "Models" },
  { href: "/keys", label: "API Keys" },
  { href: "/quota", label: "Quota" },
] as const;

export function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--border)] bg-[var(--panel)]">
      <div className="border-b border-[var(--border)] px-4 py-5">
        <div className="text-sm font-semibold tracking-wide text-[var(--accent)]">
          Perzforge
        </div>
        <div className="mt-1 truncate text-xs text-[var(--muted)]">
          {user?.email ?? "…"}
        </div>
      </div>
      <nav className="flex flex-1 flex-col gap-1 p-3">
        {NAV.map((item) => {
          const active =
            item.href === "/jobs"
              ? pathname === "/jobs" ||
                (pathname.startsWith("/jobs/") && !pathname.startsWith("/jobs/new"))
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded px-3 py-2 text-sm transition-colors ${
                active
                  ? "bg-[var(--accent-dim)] text-[var(--fg)]"
                  : "text-[var(--muted)] hover:bg-[var(--panel-hover)] hover:text-[var(--fg)]"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
      <div className="border-t border-[var(--border)] p-3">
        <button
          type="button"
          onClick={() => void logout()}
          className="w-full rounded px-3 py-2 text-left text-sm text-[var(--muted)] hover:bg-[var(--panel-hover)] hover:text-[var(--fg)]"
        >
          Logout
        </button>
      </div>
    </aside>
  );
}
