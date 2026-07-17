import {
  ApiKey,
  ApiKeyCreated,
  CreateApiKeyPayload,
  Job,
  JobList,
  MeQuota,
  PASSWORD_CHANGE_REQUIRED,
  SubmitJobPayload,
  TokenResponse,
  User,
} from "./types";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export function isPasswordChangeRequired(err: unknown): boolean {
  return (
    err instanceof ApiError &&
    err.status === 403 &&
    err.detail.toLowerCase() === PASSWORD_CHANGE_REQUIRED
  );
}

type TokenGetter = () => string | null;
type TokenSetter = (token: string | null) => void;
type OnUnauthorized = () => void;
type OnPasswordChangeRequired = () => void;

let getAccessToken: TokenGetter = () => null;
let setAccessToken: TokenSetter = () => undefined;
let onUnauthorized: OnUnauthorized = () => undefined;
let onPasswordChangeRequired: OnPasswordChangeRequired = () => undefined;
let refreshInFlight: Promise<string | null> | null = null;

export function configureAuthHandlers(handlers: {
  getAccessToken: TokenGetter;
  setAccessToken: TokenSetter;
  onUnauthorized: OnUnauthorized;
  onPasswordChangeRequired: OnPasswordChangeRequired;
}): void {
  getAccessToken = handlers.getAccessToken;
  setAccessToken = handlers.setAccessToken;
  onUnauthorized = handlers.onUnauthorized;
  onPasswordChangeRequired = handlers.onPasswordChangeRequired;
}

function apiBase(): string {
  const raw = (process.env.NEXT_PUBLIC_API_BASE ?? "").trim();
  if (!raw) {
    return "";
  }
  // Bare host:port without a scheme is treated as a relative path by the browser
  // (e.g. "100.x.x.x:8000/api/..." → 404 on the Next origin). Normalize or ignore.
  if (!/^https?:\/\//i.test(raw)) {
    if (typeof console !== "undefined") {
      console.warn(
        `NEXT_PUBLIC_API_BASE="${raw}" is missing http(s)://; ignoring and using same-origin proxy`,
      );
    }
    return "";
  }
  return raw.replace(/\/$/, "");
}

function url(path: string): string {
  return `${apiBase()}${path}`;
}

async function parseDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (body.detail != null) {
      return JSON.stringify(body.detail);
    }
  } catch {
    /* ignore */
  }
  return response.statusText || "Request failed";
}

async function refreshAccessToken(): Promise<string | null> {
  if (refreshInFlight) {
    return refreshInFlight;
  }
  refreshInFlight = (async () => {
    const response = await fetch(url("/api/v1/auth/refresh"), {
      method: "POST",
      credentials: "include",
    });
    if (!response.ok) {
      setAccessToken(null);
      return null;
    }
    const data = (await response.json()) as TokenResponse;
    setAccessToken(data.access_token);
    return data.access_token;
  })().finally(() => {
    refreshInFlight = null;
  });
  return refreshInFlight;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  { retry = true, auth = true }: { retry?: boolean; auth?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (auth) {
    const token = getAccessToken();
    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }

  const response = await fetch(url(path), {
    ...init,
    headers,
    credentials: "include",
  });

  if (response.status === 401 && auth && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      return request<T>(path, init, { retry: false, auth });
    }
    onUnauthorized();
    throw new ApiError(401, await parseDetail(response));
  }

  if (response.status === 403) {
    const detail = await parseDetail(response);
    if (detail.toLowerCase() === PASSWORD_CHANGE_REQUIRED) {
      onPasswordChangeRequired();
      throw new ApiError(403, detail);
    }
    throw new ApiError(403, detail);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseDetail(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export const api = {
  login(email: string, password: string): Promise<TokenResponse> {
    return request<TokenResponse>(
      "/api/v1/auth/login",
      { method: "POST", body: JSON.stringify({ email, password }) },
      { auth: false },
    );
  },

  logout(): Promise<void> {
    return request<void>("/api/v1/auth/logout", { method: "POST" }, { auth: false });
  },

  me(): Promise<User> {
    return request<User>("/api/v1/auth/me");
  },

  changePassword(old_password: string, new_password: string): Promise<void> {
    return request<void>("/api/v1/auth/change-password", {
      method: "POST",
      body: JSON.stringify({ old_password, new_password }),
    });
  },

  listJobs(limit = 50, offset = 0): Promise<JobList> {
    return request<JobList>(`/api/v1/jobs?limit=${limit}&offset=${offset}`);
  },

  getJob(id: string): Promise<Job> {
    return request<Job>(`/api/v1/jobs/${id}`);
  },

  submitJob(payload: SubmitJobPayload): Promise<Job> {
    return request<Job>("/api/v1/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  cancelJob(id: string): Promise<Job> {
    return request<Job>(`/api/v1/jobs/${id}/cancel`, { method: "POST" });
  },

  listKeys(): Promise<ApiKey[]> {
    return request<ApiKey[]>("/api/v1/keys");
  },

  createKey(payload: CreateApiKeyPayload): Promise<ApiKeyCreated> {
    return request<ApiKeyCreated>("/api/v1/keys", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  deleteKey(id: string): Promise<void> {
    return request<void>(`/api/v1/keys/${id}`, { method: "DELETE" });
  },

  getQuota(): Promise<MeQuota> {
    return request<MeQuota>("/api/v1/me/quota");
  },
};

export function jobLogsWsUrl(jobId: string, accessToken: string): string {
  const configured = process.env.NEXT_PUBLIC_WS_BASE?.replace(/\/$/, "");
  if (configured) {
    return `${configured}/api/v1/jobs/${jobId}/logs?token=${encodeURIComponent(accessToken)}`;
  }
  if (typeof window === "undefined") {
    return "";
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}/api/v1/jobs/${jobId}/logs?token=${encodeURIComponent(accessToken)}`;
}

export { refreshAccessToken };
