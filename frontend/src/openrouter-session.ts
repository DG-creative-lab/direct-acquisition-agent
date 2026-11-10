export type OpenRouterModel = {
  id: string;
  name: string;
  tier: "Free" | "Lower cost" | "Standard";
  input: number;
  output: number;
};

export type OpenRouterSession = {
  handle: string;
  binding: string;
  session: string;
  model?: Pick<OpenRouterModel, "id" | "name" | "tier">;
};

const storageKey = "workspace-openrouter";
const sessionIdKey = "workspace-openrouter-session";

export function openRouterSessionId() {
  const saved = sessionStorage.getItem(sessionIdKey);
  if (saved) return saved;
  const session = crypto.randomUUID();
  sessionStorage.setItem(sessionIdKey, session);
  return session;
}

export function openRouterSession(): OpenRouterSession | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(storageKey) ?? "null");
    // Remove credentials left by the earlier browser-storage implementation.
    if (typeof saved?.key === "string") sessionStorage.removeItem(storageKey);
    return typeof saved?.handle === "string" &&
      typeof saved.binding === "string" &&
      typeof saved.session === "string"
      ? saved
      : null;
  } catch {
    return null;
  }
}

export function saveOpenRouterSession(value: OpenRouterSession | null) {
  if (value) sessionStorage.setItem(storageKey, JSON.stringify(value));
  else sessionStorage.removeItem(storageKey);
}

export function openRouterHeaders(value: OpenRouterSession | null) {
  const headers: Record<string, string> = {};
  if (value) {
    headers["X-OpenRouter-Handle"] = value.handle;
    headers["X-OpenRouter-Session"] = value.session;
    if (value.model) {
      headers["X-OpenRouter-Model"] = value.model.id;
      headers["X-OpenRouter-Tier"] = value.model.tier;
    }
  }
  return headers;
}
