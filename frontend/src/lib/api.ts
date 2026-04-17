const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type JsonPrimitive = string | number | boolean | null;
type JsonValue = JsonPrimitive | JsonValue[] | { [key: string]: JsonValue };

type RequestJsonOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: JsonValue;
  signal?: AbortSignal;
  timeoutMs?: number;
};

export class ApiError extends Error {
  status: number;
  body?: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

function toUrl(path: string): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}

function withTimeoutSignal(signal?: AbortSignal, timeoutMs = 15000): AbortSignal {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  const abortFromParent = () => controller.abort();
  if (signal) {
    if (signal.aborted) {
      controller.abort();
    } else {
      signal.addEventListener("abort", abortFromParent, { once: true });
    }
  }

  controller.signal.addEventListener(
    "abort",
    () => {
      clearTimeout(timeoutId);
      if (signal) signal.removeEventListener("abort", abortFromParent);
    },
    { once: true }
  );

  return controller.signal;
}

async function parseErrorBody(res: Response): Promise<unknown> {
  const contentType = res.headers.get("content-type") ?? "";
  try {
    if (contentType.includes("application/json")) {
      return await res.json();
    }
    const text = await res.text();
    return text || undefined;
  } catch {
    return undefined;
  }
}

function errorMessage(status: number, body: unknown): string {
  if (typeof body === "string" && body.trim()) return body;
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return `Request failed (${status})`;
}

export async function requestJson<T>(
  path: string,
  options: RequestJsonOptions = {}
): Promise<T> {
  const { method = "GET", body, signal, timeoutMs } = options;
  const res = await fetch(toUrl(path), {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: withTimeoutSignal(signal, timeoutMs),
  });

  if (!res.ok) {
    const bodyData = await parseErrorBody(res);
    throw new ApiError(errorMessage(res.status, bodyData), res.status, bodyData);
  }

  return (await res.json()) as T;
}

export async function requestSSE(
  path: string,
  options: Pick<RequestJsonOptions, "method" | "body" | "signal" | "timeoutMs"> = {}
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const { method = "POST", body, signal, timeoutMs = 60000 } = options;
  const res = await fetch(toUrl(path), {
    method,
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    signal: withTimeoutSignal(signal, timeoutMs),
  });

  if (!res.ok || !res.body) {
    const bodyData = await parseErrorBody(res);
    throw new ApiError(errorMessage(res.status, bodyData), res.status, bodyData);
  }

  return res.body.getReader();
}

export type DashboardData = {
  has_data: boolean;
  date_range: { start: string; end: string } | null;
  dining: Array<{
    date: string;
    restaurant: string;
    dishes: string[];
    meal_type: string;
    sentiment: number;
    description: string;
  }>;
  reflections: Array<{
    date: string;
    topic: string;
    content: string;
    is_actionable: boolean;
  }>;
  learning: Array<{
    date: string;
    subject: string;
    milestone: string;
    description: string;
    sentiment: number;
  }>;
};

export type NarrativeData = {
  content: string;
  week_start: string;
  week_end: string;
  generated_at: string | null;
  cached: boolean;
};

export type ChatSessionSummary = {
  id: string;
  title: string | null;
  is_temporary: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
};

export type ChatSessionMessage = {
  id: number;
  role: "user" | "assistant" | string;
  content: string;
  retrieved_context?: unknown[];
  created_at: string;
};

export type ChatSessionDetail = {
  id: string;
  title: string | null;
  messages: ChatSessionMessage[];
};

function withRefDate(path: string, refDate?: string): string {
  if (!refDate) return path;
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}ref_date=${encodeURIComponent(refDate)}`;
}

export async function getDashboardData(
  signal?: AbortSignal,
  refDate?: string
): Promise<DashboardData> {
  return requestJson<DashboardData>(withRefDate("/api/dashboard/data", refDate), { signal });
}

export async function getDashboardNarrative(
  signal?: AbortSignal,
  refDate?: string
): Promise<NarrativeData> {
  return requestJson<NarrativeData>(withRefDate("/api/dashboard/narrative", refDate), { signal });
}

export async function listChatSessions(signal?: AbortSignal): Promise<ChatSessionSummary[]> {
  return requestJson<ChatSessionSummary[]>("/api/chat/sessions", { signal });
}

export async function createChatSession(
  title: string | null = null,
  is_temporary: boolean = false,
  signal?: AbortSignal
): Promise<ChatSessionSummary> {
  return requestJson<ChatSessionSummary>("/api/chat/sessions", {
    method: "POST",
    body: { title, is_temporary },
    signal,
  });
}

export async function getChatSession(
  id: string,
  signal?: AbortSignal
): Promise<ChatSessionDetail> {
  return requestJson<ChatSessionDetail>(`/api/chat/sessions/${id}`, { signal });
}

export async function saveTempSession(id: string, signal?: AbortSignal): Promise<ChatSessionSummary> {
  return requestJson<ChatSessionSummary>(`/api/chat/sessions/${id}/save`, {
    method: "PATCH",
    signal,
  });
}

export async function deleteChatSession(id: string, signal?: AbortSignal): Promise<void> {
  await requestJson<{ status: string }>(`/api/chat/sessions/${id}`, {
    method: "DELETE",
    signal,
  });
}

export async function postChatMessageStream(
  sessionId: string,
  content: string,
  mode: string = "default",
  signal?: AbortSignal
): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  return requestSSE(`/api/chat/sessions/${sessionId}/message`, {
    method: "POST",
    body: { content, mode },
    signal,
  });
}

export { API_BASE_URL };
