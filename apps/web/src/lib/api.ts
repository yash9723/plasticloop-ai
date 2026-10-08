import { useAuth } from "@/lib/auth-store";
import { toQuery } from "@/lib/utils";

/** Error returned by the API in the shared `{error: {code, message, details, request_id}}` shape. */
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** The request never reached the server (offline, DNS, server down). */
export class NetworkError extends Error {
  constructor(message = "Network unavailable") {
    super(message);
    this.name = "NetworkError";
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;
export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  form?: FormData;
  query?: Query;
  signal?: AbortSignal;
  auth?: boolean;
  headers?: Record<string, string>;
}

const REFRESHABLE = new Set(["TOKEN_EXPIRED", "NOT_AUTHENTICATED", "INVALID_TOKEN"]);
let refreshing: Promise<boolean> | null = null;

/** Rotates the httpOnly refresh cookie and stores a new access token. Single-flight across concurrent callers. */
export function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      let res: Response;
      try {
        res = await fetch("/api/v1/auth/refresh", {
          method: "POST",
          headers: { "X-Requested-With": "plasticloop" },
          credentials: "same-origin",
        });
      } catch {
        throw new NetworkError();
      }
      if (!res.ok) {
        useAuth.getState().clear();
        return false;
      }
      const data = await res.json();
      useAuth.getState().setSession(data.access_token, data.user);
      return true;
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

async function toApiError(res: Response): Promise<ApiError> {
  try {
    const data = await res.json();
    const e = data?.error ?? {};
    return new ApiError(res.status, e.code ?? "HTTP_ERROR", e.message ?? res.statusText, e.details, e.request_id);
  } catch {
    return new ApiError(res.status, "HTTP_ERROR", res.statusText || `HTTP ${res.status}`);
  }
}

async function send(path: string, opts: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = { ...(opts.headers ?? {}) };
  const token = useAuth.getState().accessToken;
  if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  try {
    return await fetch(`/api/v1${path}${opts.query ? toQuery(opts.query) : ""}`, {
      method: opts.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: opts.signal,
      credentials: "same-origin",
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new NetworkError();
  }
}

export async function api<T = unknown>(path: string, opts: RequestOptions = {}): Promise<T> {
  let res = await send(path, opts);
  if (res.status === 401 && opts.auth !== false) {
    const code = await res
      .clone()
      .json()
      .then((d) => d?.error?.code)
      .catch(() => undefined);
    if (REFRESHABLE.has(code) && (await refreshSession())) res = await send(path, opts);
  }
  if (!res.ok) throw await toApiError(res);
  if (res.status === 204) return undefined as T;
  return (res.headers.get("content-type")?.includes("application/json") ? res.json() : res.blob()) as Promise<T>;
}

/** Authenticated file download (CSV/PDF) that keeps the token out of the URL. */
export async function downloadFile(path: string, filename: string, query?: Query) {
  const blob = await api<Blob>(path, { query });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export function errorMessage(err: unknown, fallback = "Something went wrong"): string {
  if (err instanceof ApiError || err instanceof NetworkError) return err.message;
  if (err instanceof Error) return err.message || fallback;
  return fallback;
}
