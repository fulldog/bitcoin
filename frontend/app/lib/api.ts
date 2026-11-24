export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const authListeners = new Set<() => void>();

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem("quant_token");
}

export function subscribeAuth(listener: () => void): () => void {
  authListeners.add(listener);
  return () => authListeners.delete(listener);
}

export function publishAuth(token: string | null): void {
  if (token) window.sessionStorage.setItem("quant_token", token);
  else window.sessionStorage.removeItem("quant_token");
  authListeners.forEach((listener) => listener());
}

function authHeaders(): HeadersInit {
  const token = readToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function failure(path: string, response: Response): Promise<never> {
  if (response.status === 401) {
    publishAuth(null);
  }
  let detail = "";
  try {
    const body = await response.json() as { detail?: unknown };
    if (typeof body.detail === "string") detail = body.detail;
  } catch {
    detail = "";
  }
  throw new Error(detail || `接口 ${path} 返回 ${response.status}`);
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", headers: authHeaders() });
  if (!response.ok) return failure(path, response);
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown, key: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key, ...authHeaders() },
    body: JSON.stringify(body),
  });
  if (!response.ok) return failure(path, response);
  return response.json() as Promise<T>;
}

export async function login(username: string, password: string): Promise<void> {
  const response = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) throw new Error("账号或密码不正确");
  const body = await response.json() as { access_token: string };
  publishAuth(body.access_token);
}
