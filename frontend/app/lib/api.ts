export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`接口 ${path} 返回 ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function postJson<T>(path: string, body: unknown, key: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", "Idempotency-Key": key },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`接口 ${path} 返回 ${response.status}`);
  }
  return response.json() as Promise<T>;
}
