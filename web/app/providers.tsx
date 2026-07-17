"use client";

import { Suspense, type ReactNode } from "react";

import { AuthProvider } from "@/lib/auth";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={null}>
      <AuthProvider>{children}</AuthProvider>
    </Suspense>
  );
}
