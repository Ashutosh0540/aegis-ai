/**
 * Typed API client for the AegisAI backend.
 *
 * Centralized so every page/component makes requests the same way (base
 * URL, auth header injection, error shape) rather than scattering raw
 * fetch calls across the app.
 */
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_email_verified: boolean;
  created_at: string;
}

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem("aegis_access_token");
}

export function setTokens(tokens: TokenPair) {
  window.localStorage.setItem("aegis_access_token", tokens.access_token);
  window.localStorage.setItem("aegis_refresh_token", tokens.refresh_token);
}

export function clearTokens() {
  window.localStorage.removeItem("aegis_access_token");
  window.localStorage.removeItem("aegis_refresh_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  authenticated = false
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");

  if (authenticated) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export const api = {
  register: (data: { email: string; password: string; full_name: string }) =>
    request<User>("/auth/register", { method: "POST", body: JSON.stringify(data) }),

  login: async (email: string, password: string) => {
    const form = new URLSearchParams();
    form.set("username", email);
    form.set("password", password);
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: form.toString(),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({ detail: res.statusText }));
      throw new ApiError(res.status, body.detail ?? "Login failed");
    }
    const tokens = (await res.json()) as TokenPair;
    setTokens(tokens);
    return tokens;
  },

  me: () => request<User>("/users/me", {}, true),

  createOrganization: (name: string) =>
    request<Organization>("/organizations", { method: "POST", body: JSON.stringify({ name }) }, true),

  listOrganizations: () => request<Organization[]>("/organizations", {}, true),
};

export interface DocumentVersion {
  id: string;
  version_number: number;
  size_bytes: number;
  checksum_sha256: string;
  status: "pending" | "processing" | "completed" | "failed" | "needs_ocr";
  error_message: string | null;
  page_count: number | null;
  created_at: string;
}

export interface DocumentSummary {
  id: string;
  organization_id: string;
  uploaded_by_id: string;
  filename: string;
  content_type: string;
  latest_version_number: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentDetail extends DocumentSummary {
  latest_version: DocumentVersion | null;
}

async function requestForm<T>(path: string, formData: FormData): Promise<T> {
  const token = getAccessToken();
  const headers = new Headers();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers,
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, body.detail ?? "Request failed");
  }
  return res.json() as Promise<T>;
}

export const documentsApi = {
  upload: (orgId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return requestForm<DocumentSummary>(`/organizations/${orgId}/documents`, form);
  },

  list: (orgId: string) =>
    request<DocumentSummary[]>(`/organizations/${orgId}/documents`, {}, true),

  get: (orgId: string, documentId: string) =>
    request<DocumentDetail>(`/organizations/${orgId}/documents/${documentId}`, {}, true),

  remove: (orgId: string, documentId: string) =>
    request<void>(`/organizations/${orgId}/documents/${documentId}`, { method: "DELETE" }, true),
};

export interface Citation {
  chunk_id: string;
  document_id: string;
  document_version_id: string;
  chunk_index: number;
  filename: string;
  score: number;
}

export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  created_at: string;
}

export interface Conversation {
  id: string;
  organization_id: string;
  created_by_id: string;
  title: string | null;
  document_id: string | null;
  created_at: string;
}

export const chatApi = {
  createConversation: (orgId: string, title?: string, documentId?: string) =>
    request<Conversation>(
      `/organizations/${orgId}/chat/conversations`,
      { method: "POST", body: JSON.stringify({ title: title ?? null, document_id: documentId ?? null }) },
      true
    ),

  listConversations: (orgId: string) =>
    request<Conversation[]>(`/organizations/${orgId}/chat/conversations`, {}, true),

  listMessages: (orgId: string, conversationId: string) =>
    request<ChatMessage[]>(
      `/organizations/${orgId}/chat/conversations/${conversationId}/messages`,
      {},
      true
    ),

  sendMessage: (orgId: string, conversationId: string, content: string) =>
    request<ChatMessage>(
      `/organizations/${orgId}/chat/conversations/${conversationId}/messages`,
      { method: "POST", body: JSON.stringify({ content }) },
      true
    ),
};

export interface Ticket {
  id: string;
  organization_id: string;
  created_by_id: string;
  assigned_to_id: string | null;
  title: string;
  description: string;
  status: "open" | "in_progress" | "resolved" | "closed";
  priority: "low" | "medium" | "high" | "urgent";
  source: "manual" | "agent";
  created_at: string;
  updated_at: string;
}

export const ticketsApi = {
  create: (orgId: string, title: string, description: string, priority: Ticket["priority"] = "medium") =>
    request<Ticket>(
      `/organizations/${orgId}/tickets`,
      { method: "POST", body: JSON.stringify({ title, description, priority }) },
      true
    ),

  list: (orgId: string) => request<Ticket[]>(`/organizations/${orgId}/tickets`, {}, true),

  update: (orgId: string, ticketId: string, patch: Partial<Pick<Ticket, "status" | "priority">>) =>
    request<Ticket>(
      `/organizations/${orgId}/tickets/${ticketId}`,
      { method: "PATCH", body: JSON.stringify(patch) },
      true
    ),
};

export { ApiError };
