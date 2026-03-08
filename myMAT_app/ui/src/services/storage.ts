import type { AuthUser, ChatThread } from "../types";

const USERS_KEY = "mymat_users_v1";
const CURRENT_USER_KEY = "mymat_current_user_v1";
const THREADS_PREFIX = "mymat_threads_v1:";
const ACTIVE_THREAD_PREFIX = "mymat_active_thread_v1:";

function threadsKey(username: string): string {
  return `${THREADS_PREFIX}${username}`;
}

function activeThreadKey(username: string): string {
  return `${ACTIVE_THREAD_PREFIX}${username}`;
}

function parseJson<T>(raw: string | null, fallback: T): T {
  if (!raw) {
    return fallback;
  }
  try {
    return JSON.parse(raw) as T;
  } catch {
    return fallback;
  }
}

function isBrowser(): boolean {
  return typeof window !== "undefined" && typeof window.localStorage !== "undefined";
}

function toHex(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function fallbackHash(input: string): string {
  // Non-crypto fallback for non-secure contexts (HTTP/IP deployments).
  let h1 = 5381;
  let h2 = 52711;
  for (let i = 0; i < input.length; i += 1) {
    const c = input.charCodeAt(i);
    h1 = (h1 * 33) ^ c;
    h2 = (h2 * 31) ^ c;
  }
  return `fallback-${(h1 >>> 0).toString(16)}${(h2 >>> 0).toString(16)}`;
}

export async function hashPassword(password: string): Promise<string> {
  const normalized = password.trim();
  if (
    typeof globalThis.crypto !== "undefined" &&
    globalThis.crypto.subtle &&
    typeof globalThis.crypto.subtle.digest === "function"
  ) {
    const digest = await globalThis.crypto.subtle.digest(
      "SHA-256",
      new TextEncoder().encode(normalized),
    );
    return toHex(digest);
  }
  return fallbackHash(normalized);
}

export function getUsers(): AuthUser[] {
  if (!isBrowser()) {
    return [];
  }
  return parseJson<AuthUser[]>(window.localStorage.getItem(USERS_KEY), []);
}

export function saveUsers(users: AuthUser[]): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(USERS_KEY, JSON.stringify(users));
}

export function getCurrentUser(): string | null {
  if (!isBrowser()) {
    return null;
  }
  return window.localStorage.getItem(CURRENT_USER_KEY);
}

export function setCurrentUser(username: string): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(CURRENT_USER_KEY, username);
}

export function clearCurrentUser(): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.removeItem(CURRENT_USER_KEY);
}

export function getThreadsForUser(username: string): {
  threads: ChatThread[];
  recoveredFromCorruption: boolean;
} {
  if (!isBrowser()) {
    return { threads: [], recoveredFromCorruption: false };
  }

  const key = threadsKey(username);
  const raw = window.localStorage.getItem(key);
  if (!raw) {
    return { threads: [], recoveredFromCorruption: false };
  }

  try {
    const parsed = JSON.parse(raw) as ChatThread[];
    if (!Array.isArray(parsed)) {
      throw new Error("threads payload is not an array");
    }
    return { threads: parsed, recoveredFromCorruption: false };
  } catch {
    window.localStorage.removeItem(key);
    return { threads: [], recoveredFromCorruption: true };
  }
}

export function saveThreadsForUser(username: string, threads: ChatThread[]): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(threadsKey(username), JSON.stringify(threads));
}

export function getActiveThreadId(username: string): string | null {
  if (!isBrowser()) {
    return null;
  }
  return window.localStorage.getItem(activeThreadKey(username));
}

export function setActiveThreadId(username: string, threadId: string): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(activeThreadKey(username), threadId);
}
