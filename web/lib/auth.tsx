"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { usePathname, useRouter } from "next/navigation";

import {
  api,
  configureAuthHandlers,
  isPasswordChangeRequired,
  refreshAccessToken,
} from "./api";
import type { User } from "./types";

interface AuthContextValue {
  accessToken: string | null;
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  setAccessToken: (token: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

const PUBLIC_PATHS = new Set(["/login", "/change-password"]);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const tokenRef = useRef<string | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const setAccessToken = useCallback((token: string | null) => {
    tokenRef.current = token;
    setAccessTokenState(token);
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    setAccessToken(null);
    setUser(null);
    router.replace("/login");
  }, [router, setAccessToken]);

  const refreshUser = useCallback(async () => {
    const me = await api.me();
    setUser(me);
    if (me.must_change_password && pathname !== "/change-password") {
      router.replace("/change-password");
    }
  }, [pathname, router]);

  useEffect(() => {
    configureAuthHandlers({
      getAccessToken: () => tokenRef.current,
      setAccessToken,
      onUnauthorized: () => {
        setAccessToken(null);
        setUser(null);
        if (!PUBLIC_PATHS.has(pathname)) {
          router.replace("/login");
        }
      },
      onPasswordChangeRequired: () => {
        router.replace("/change-password");
      },
    });
  }, [pathname, router, setAccessToken]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const token = await refreshAccessToken();
        if (cancelled) {
          return;
        }
        if (token) {
          setAccessToken(token);
          try {
            await refreshUser();
          } catch (err) {
            if (isPasswordChangeRequired(err)) {
              return;
            }
            setAccessToken(null);
          }
        }
      } finally {
        if (!cancelled) {
          setReady(true);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [refreshUser, setAccessToken]);

  useEffect(() => {
    if (!ready) {
      return;
    }
    if (!accessToken && !PUBLIC_PATHS.has(pathname)) {
      router.replace("/login");
    }
  }, [accessToken, pathname, ready, router]);

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await api.login(email, password);
      setAccessToken(tokens.access_token);
      try {
        const me = await api.me();
        setUser(me);
        if (me.must_change_password) {
          router.replace("/change-password");
          return;
        }
        router.replace("/jobs");
      } catch (err) {
        if (isPasswordChangeRequired(err)) {
          router.replace("/change-password");
          return;
        }
        throw err;
      }
    },
    [router, setAccessToken],
  );

  const value = useMemo(
    () => ({
      accessToken,
      user,
      ready,
      login,
      logout,
      refreshUser,
      setAccessToken,
    }),
    [accessToken, user, ready, login, logout, refreshUser, setAccessToken],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return ctx;
}
