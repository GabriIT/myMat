import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  createThread,
  deleteThread,
  getThreadMessages,
  listThreads,
  queryMat,
  renameThread,
} from "../services/api";
import { getActiveThreadId, setActiveThreadId } from "../services/storage";
import type {
  AgentHint,
  ChatModelOption,
  ChatThread,
  MatFormPayload,
  MatQueryResponse,
  ThreadMessage,
  ThreadMessageApi,
  ThreadSummaryApi,
} from "../types";

const ERROR_FALLBACK =
  "The backend request failed. Please retry. Check API server and network connectivity.";

function newId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function makeTitle(question: string): string {
  const clean = question.trim().replace(/\s+/g, " ");
  if (!clean) {
    return "New Thread";
  }
  return clean.length > 48 ? `${clean.slice(0, 48)}...` : clean;
}

function sortThreads(threads: ChatThread[]): ChatThread[] {
  return [...threads].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
}

function upsertThread(threads: ChatThread[], updatedThread: ChatThread): ChatThread[] {
  const rest = threads.filter((thread) => thread.id !== updatedThread.id);
  return sortThreads([updatedThread, ...rest]);
}

function toHistory(messages: ThreadMessage[]): Array<{ role: "user" | "assistant"; content: string }> {
  return messages.map((message) => ({ role: message.role, content: message.content }));
}

function mapSummaryToThread(summary: ThreadSummaryApi): ChatThread {
  return {
    id: summary.thread_id,
    title: summary.title || "New Thread",
    createdAt: summary.created_at,
    updatedAt: summary.updated_at,
    messages: [],
  };
}

function mapApiMessage(message: ThreadMessageApi): ThreadMessage {
  return {
    id: `db-${message.id}`,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
    structured: message.structured,
    sources: message.sources ?? [],
    routedAgent: message.routed_agent,
  };
}

function mergeThreadSummary(base: ChatThread, summary: ThreadSummaryApi): ChatThread {
  return {
    ...base,
    title: summary.title || base.title || "New Thread",
    createdAt: summary.created_at || base.createdAt,
    updatedAt: summary.updated_at || base.updatedAt,
  };
}

export function useThreads(username: string | null) {
  const [threads, setThreads] = useState<ChatThread[]>([]);
  const [activeThreadId, setActiveThreadIdState] = useState<string | null>(null);
  const [storageWarning, setStorageWarning] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const loadedThreadIdsRef = useRef(new Set<string>());
  const loadingThreadIdsRef = useRef(new Set<string>());
  const interactionVersionRef = useRef(0);

  const loadThreadMessagesForId = useCallback(
    async (threadId: string, force = false): Promise<void> => {
      if (!username) {
        return;
      }
      if (!threadId.trim()) {
        return;
      }
      if (!force && loadedThreadIdsRef.current.has(threadId)) {
        return;
      }
      if (loadingThreadIdsRef.current.has(threadId)) {
        return;
      }
      loadingThreadIdsRef.current.add(threadId);
      try {
        const payload = await getThreadMessages(username, threadId, 500);
        const messages = payload.messages.map(mapApiMessage);
        const mappedSummary = mapSummaryToThread(payload.thread);
        const hydrated: ChatThread = { ...mappedSummary, messages };
        setThreads((prev) => {
          const existing = prev.find((item) => item.id === threadId);
          if (!existing) {
            return upsertThread(prev, hydrated);
          }
          return upsertThread(prev, { ...mergeThreadSummary(existing, payload.thread), messages });
        });
        loadedThreadIdsRef.current.add(threadId);
        setStorageWarning(null);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        setStorageWarning(`Thread sync warning: ${message}`);
      } finally {
        loadingThreadIdsRef.current.delete(threadId);
      }
    },
    [username],
  );

  useEffect(() => {
    let cancelled = false;

    async function loadInitialThreads(): Promise<void> {
      if (!username) {
        setThreads([]);
        setActiveThreadIdState(null);
        setStorageWarning(null);
        loadedThreadIdsRef.current = new Set<string>();
        loadingThreadIdsRef.current = new Set<string>();
        return;
      }

      const loadVersion = interactionVersionRef.current;
      try {
        const summaries = await listThreads(username, 100);
        if (cancelled) {
          return;
        }
        if (interactionVersionRef.current !== loadVersion) {
          return;
        }
        const orderedThreads = sortThreads(summaries.map(mapSummaryToThread));
        setThreads(orderedThreads);
        loadedThreadIdsRef.current = new Set<string>();
        loadingThreadIdsRef.current = new Set<string>();

        const storedActive = getActiveThreadId(username);
        const defaultActive =
          storedActive && orderedThreads.some((t) => t.id === storedActive)
            ? storedActive
            : orderedThreads[0]?.id ?? null;

        setActiveThreadIdState(defaultActive);
        setStorageWarning(null);

        if (defaultActive) {
          void loadThreadMessagesForId(defaultActive, true);
        }
      } catch (error) {
        if (cancelled) {
          return;
        }
        setThreads([]);
        setActiveThreadIdState(null);
        const message = error instanceof Error ? error.message : "Unknown error";
        setStorageWarning(`Thread sync warning: ${message}`);
      }
    }

    void loadInitialThreads();
    return () => {
      cancelled = true;
    };
  }, [username, loadThreadMessagesForId]);

  useEffect(() => {
    if (!username || !activeThreadId) {
      return;
    }
    setActiveThreadId(username, activeThreadId);
  }, [username, activeThreadId]);

  const activeThread = useMemo(
    () => threads.find((thread) => thread.id === activeThreadId) ?? null,
    [activeThreadId, threads],
  );

  async function createThreadFromApi(): Promise<string | null> {
    if (!username) {
      return null;
    }
    try {
      const threadSummary = await createThread({ username, title: "New Thread" });
      const thread = mapSummaryToThread(threadSummary);
      interactionVersionRef.current += 1;
      setThreads((prev) => upsertThread(prev, thread));
      setActiveThreadIdState(thread.id);
      loadedThreadIdsRef.current.add(thread.id);
      setStorageWarning(null);
      return thread.id;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setStorageWarning(`Thread sync warning: ${message}`);
      return null;
    }
  }

  function createThreadForUi(): void {
    void createThreadFromApi();
  }

  function selectThread(threadId: string): void {
    setActiveThreadIdState(threadId);
    void loadThreadMessagesForId(threadId, false);
  }

  async function renameThreadForUi(threadId: string, currentTitle: string): Promise<void> {
    if (!username) {
      return;
    }
    const proposed = window.prompt("Rename thread", currentTitle) ?? "";
    const newTitle = proposed.trim();
    if (!newTitle || newTitle === currentTitle.trim()) {
      return;
    }
    try {
      const summary = await renameThread(threadId, { username, title: newTitle });
      interactionVersionRef.current += 1;
      setThreads((prev) => {
        const existing = prev.find((item) => item.id === threadId);
        if (!existing) {
          return prev;
        }
        return upsertThread(prev, mergeThreadSummary(existing, summary));
      });
      setStorageWarning(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setStorageWarning(`Thread sync warning: ${message}`);
    }
  }

  async function deleteThreadForUi(threadId: string): Promise<void> {
    if (!username) {
      return;
    }
    const confirmed = window.confirm("Delete this thread? This cannot be undone.");
    if (!confirmed) {
      return;
    }
    try {
      await deleteThread(username, threadId);
      interactionVersionRef.current += 1;
      const updatedThreads = sortThreads(threads.filter((item) => item.id !== threadId));
      setThreads(updatedThreads);
      if (activeThreadId === threadId) {
        const nextActive = updatedThreads[0]?.id ?? null;
        setActiveThreadIdState(nextActive);
        if (nextActive) {
          void loadThreadMessagesForId(nextActive, false);
        }
      }
      setStorageWarning(null);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      setStorageWarning(`Thread sync warning: ${message}`);
    }
  }

  async function sendQuery(
    questionInput: string,
    chatModel: ChatModelOption,
    selectedAgentHint: AgentHint,
    formPayload?: MatFormPayload,
  ): Promise<void> {
    const question = questionInput.trim();
    if (!question || !username || isSending) {
      return;
    }

    setIsSending(true);
    setStorageWarning(null);

    let baseThread = activeThreadId
      ? threads.find((thread) => thread.id === activeThreadId) ?? null
      : null;

    if (!baseThread) {
      const createdThreadId = await createThreadFromApi();
      if (!createdThreadId) {
        setIsSending(false);
        return;
      }
      baseThread = {
        id: createdThreadId,
        title: "New Thread",
        createdAt: nowIso(),
        updatedAt: nowIso(),
        messages: [],
      };
    }

    const userMessage: ThreadMessage = {
      id: newId(),
      role: "user",
      content: question,
      createdAt: nowIso(),
    };

    const priorHistory = toHistory(baseThread.messages);

    const withUserMessage: ChatThread = {
      ...baseThread,
      title: baseThread.messages.length === 0 ? makeTitle(question) : baseThread.title,
      updatedAt: nowIso(),
      messages: [...baseThread.messages, userMessage],
    };

    interactionVersionRef.current += 1;
    setActiveThreadIdState(withUserMessage.id);
    setThreads((prev) => upsertThread(prev, withUserMessage));

    try {
      const response: MatQueryResponse = await queryMat({
        message: question,
        history: priorHistory,
        chat_model: chatModel,
        selected_agent_hint: selectedAgentHint,
        username,
        thread_id: withUserMessage.id,
        form_payload: formPayload,
      });
      const assistantMessage: ThreadMessage = {
        id: newId(),
        role: "assistant",
        content: response.answer_text,
        createdAt: nowIso(),
        structured: {
          prompt: question,
          bullets: response.bullets,
          answer_text: response.answer_text,
        },
        sources: response.sources,
        routedAgent: response.meta.routed_agent,
      };

      const completedThread: ChatThread = {
        ...withUserMessage,
        updatedAt: nowIso(),
        messages: [...withUserMessage.messages, assistantMessage],
      };
      interactionVersionRef.current += 1;
      setThreads((prev) => upsertThread(prev, completedThread));
      void loadThreadMessagesForId(withUserMessage.id, true);
    } catch (error) {
      const assistantMessage: ThreadMessage = {
        id: newId(),
        role: "assistant",
        content:
          error instanceof Error && error.message ? `${ERROR_FALLBACK}\n${error.message}` : ERROR_FALLBACK,
        createdAt: nowIso(),
      };
      const failedThread: ChatThread = {
        ...withUserMessage,
        updatedAt: nowIso(),
        messages: [...withUserMessage.messages, assistantMessage],
      };
      interactionVersionRef.current += 1;
      setThreads((prev) => upsertThread(prev, failedThread));
    } finally {
      setIsSending(false);
    }
  }

  return {
    threads,
    activeThread,
    activeThreadId,
    storageWarning,
    isSending,
    createThread: createThreadForUi,
    selectThread,
    renameThread: renameThreadForUi,
    deleteThread: deleteThreadForUi,
    sendQuery,
  };
}
