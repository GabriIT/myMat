import { useMemo, useState } from "react";

import type { ChatThread } from "../types";

interface ThreadSidebarProps {
  username: string;
  threads: ChatThread[];
  activeThreadId: string | null;
  mobileOpen: boolean;
  onToggleMobile: () => void;
  onCreateThread: () => void;
  onSelectThread: (threadId: string) => void;
  onRenameThread: (threadId: string, currentTitle: string) => void;
  onDeleteThread: (threadId: string) => void;
  onLogout: () => void;
}

function formatUpdatedAt(isoDate: string): string {
  const date = new Date(isoDate);
  return date.toLocaleString();
}

export function ThreadSidebar({
  username,
  threads,
  activeThreadId,
  mobileOpen,
  onToggleMobile,
  onCreateThread,
  onSelectThread,
  onRenameThread,
  onDeleteThread,
  onLogout,
}: ThreadSidebarProps) {
  const [actionsOpen, setActionsOpen] = useState(false);
  const sorted = [...threads].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime(),
  );
  const selectedThread = useMemo(
    () => sorted.find((thread) => thread.id === activeThreadId) ?? null,
    [activeThreadId, sorted],
  );

  return (
    <aside className={`sidebar ${mobileOpen ? "open" : ""}`}>
      <div className="sidebar-top">
        <h2>Threads</h2>
        <button type="button" className="mobile-only" onClick={onToggleMobile}>
          Close
        </button>
      </div>

      <div className="sidebar-user">
        <div>
          <span className="label">Signed in</span>
          <strong>{username}</strong>
        </div>
        <button type="button" onClick={onLogout}>
          Logout
        </button>
      </div>

      <button type="button" className="new-thread" onClick={onCreateThread}>
        + New Thread
      </button>

      <div className="selected-thread-actions">
        <button
          type="button"
          className="thread-action-primary"
          onClick={() => setActionsOpen((open) => !open)}
          disabled={!selectedThread}
        >
          Selected Thread Actions
        </button>
        {actionsOpen && selectedThread ? (
          <div className="selected-thread-menu">
            <button
              type="button"
              className="thread-action-btn"
              onClick={() => {
                onRenameThread(selectedThread.id, selectedThread.title);
                setActionsOpen(false);
              }}
            >
              Rename
            </button>
            <button
              type="button"
              className="thread-action-btn danger"
              onClick={() => {
                onDeleteThread(selectedThread.id);
                setActionsOpen(false);
              }}
            >
              Delete
            </button>
          </div>
        ) : null}
      </div>

      <ul className="thread-list">
        {sorted.map((thread) => (
          <li key={thread.id}>
            <button
              type="button"
              className={thread.id === activeThreadId ? "thread-item active" : "thread-item"}
              onClick={() => {
                onSelectThread(thread.id);
                setActionsOpen(false);
              }}
            >
              <span className="thread-title">{thread.title}</span>
              <span className="thread-time">{formatUpdatedAt(thread.updatedAt)}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  );
}
