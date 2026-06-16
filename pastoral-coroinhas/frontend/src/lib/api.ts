const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

export interface ApiFetchOptions extends RequestInit {
  /** Envia Authorization Bearer (padrão: true). Use false em login e rotas públicas. */
  auth?: boolean;
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("access_token");
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("refresh_token");
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem("access_token", access);
  localStorage.setItem("refresh_token", refresh);
}

export function clearTokens() {
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  localStorage.removeItem("usuario");
}

export function saveUsuario(usuario: unknown) {
  localStorage.setItem("usuario", JSON.stringify(usuario));
}

export function getUsuario<T>(): T | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem("usuario");
  return raw ? (JSON.parse(raw) as T) : null;
}

function parseErrorMessage(body: Record<string, unknown>, status: number): string {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((e) => (typeof e === "object" && e && "msg" in e ? String((e as { msg?: string }).msg) : ""))
      .filter(Boolean);
    if (msgs.length) return msgs.join(", ");
  }
  if (status === 404) return "Serviço não encontrado. Verifique se a API está rodando.";
  return "Erro na requisição";
}

async function refreshAccessToken(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  const res = await fetch(`${API_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  });

  if (!res.ok) {
    clearTokens();
    return null;
  }

  const data = (await res.json()) as { access: string; refresh?: string };
  setTokens(data.access, data.refresh ?? refresh);
  return data.access;
}

export async function apiFetchForm<T>(
  path: string,
  formData: FormData,
  options: { auth?: boolean; method?: string } = {},
): Promise<T> {
  const { auth = true, method = "POST" } = options;
  const headers: Record<string, string> = {};
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, { method, headers, body: formData });

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    throw new ApiError(parseErrorMessage(body, res.status), res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function mediaUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (url.startsWith("http")) return url;
  const base = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(
    /\/api\/v1\/?$/,
    "",
  );
  return `${base}${url.startsWith("/") ? url : `/${url}`}`;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { auth = true, headers: optionHeaders, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((optionHeaders as Record<string, string>) || {}),
  };

  if (auth) {
    const token = getToken();
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }
  }

  async function doFetch(): Promise<Response> {
    const token = auth ? getToken() : null;
    if (auth && token) {
      headers.Authorization = `Bearer ${token}`;
    } else if (!auth) {
      delete headers.Authorization;
    }
    return fetch(`${API_URL}${path}`, { ...fetchOptions, headers });
  }

  let res = await doFetch();

  if (res.status === 401 && auth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await doFetch();
    }
  }

  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    if (res.status === 401 && auth) {
      clearTokens();
    }
    throw new ApiError(parseErrorMessage(body, res.status), res.status);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export function normalizarCpf(cpf: string): string {
  return cpf.replace(/\D/g, "");
}

export function asList<T>(data: T[] | { results?: T[] }): T[] {
  if (Array.isArray(data)) return data;
  return data.results ?? [];
}

export async function apiDownload(
  path: string,
  filename: string,
): Promise<void> {
  const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
  const res = await fetch(`${API_URL}${path}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    throw new ApiError(parseErrorMessage(body, res.status), res.status);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
