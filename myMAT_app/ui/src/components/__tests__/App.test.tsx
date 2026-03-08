import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import App from "../../App";

describe("App chat flow", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem(
      "mymat_users_v1",
      JSON.stringify([{ username: "alice", passwordHash: "hash" }]),
    );
    localStorage.setItem("mymat_current_user_v1", "alice");
    vi.restoreAllMocks();
  });

  it("sends query and renders assistant answer with source", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/threads?")) {
        return {
          ok: true,
          json: async () => ({ threads: [] }),
        };
      }
      if (url.includes("/api/catalog/customers")) {
        return {
          ok: true,
          json: async () => ({ customers: [] }),
        };
      }
      if (url.includes("/api/catalog/materials")) {
        return {
          ok: true,
          json: async () => ({ materials: [] }),
        };
      }
      if (url.includes("/api/threads") && !url.includes("/messages") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            thread: {
              thread_id: "thread-1",
              title: "New Thread",
              created_at: "2026-03-08T20:00:00.000Z",
              updated_at: "2026-03-08T20:00:00.000Z",
              message_count: 0,
              last_message_preview: null,
            },
          }),
        };
      }
      if (url.includes("/api/threads/thread-1/messages")) {
        return {
          ok: true,
          json: async () => ({
            thread: {
              thread_id: "thread-1",
              title: "What is covered?",
              created_at: "2026-03-08T20:00:00.000Z",
              updated_at: "2026-03-08T20:00:01.000Z",
              message_count: 2,
              last_message_preview: "Synthetic answer",
            },
            messages: [
              {
                id: 1,
                role: "user",
                content: "What is covered?",
                created_at: "2026-03-08T20:00:00.000Z",
              },
              {
                id: 2,
                role: "assistant",
                content: "Synthetic answer",
                created_at: "2026-03-08T20:00:01.000Z",
                structured: {
                  prompt: "What is covered?",
                  bullets: ["Synthetic bullet"],
                  answer_text: "Synthetic answer",
                },
                sources: [
                  {
                    source: "/tmp/doc.pdf",
                    source_name: "doc.pdf",
                    doc_type: "Certifications",
                    page_number: 1,
                  },
                ],
              },
            ],
          }),
        };
      }
      if (url.includes("/api/mat/query") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            routed_agent: "agent_material_queries",
            answer_text: "Synthetic answer",
            bullets: ["Synthetic bullet"],
            sources: [
              {
                source: "/tmp/doc.pdf",
                source_name: "doc.pdf",
                doc_type: "Certifications",
                page_number: 1,
              },
            ],
            follow_up_questions: [],
            meta: {
              chat_model: "gpt-4.1-nano",
              routed_agent: "agent_material_queries",
              elapsed_ms: 12,
            },
          }),
        };
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({ detail: "Not Found" }),
      };
    });

    vi.stubGlobal(
      "fetch",
      fetchMock,
    );

    render(<App />);

    fireEvent.change(screen.getByLabelText("Ask a question"), {
      target: { value: "What is covered?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalled();
    });

    expect(await screen.findByText("Synthetic answer")).toBeInTheDocument();
    expect(screen.getByText("Sources (1)")).toBeInTheDocument();
  });

  it("shows backend error fallback when request fails", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/api/threads?")) {
        return {
          ok: true,
          json: async () => ({ threads: [] }),
        };
      }
      if (url.includes("/api/catalog/customers")) {
        return {
          ok: true,
          json: async () => ({ customers: [] }),
        };
      }
      if (url.includes("/api/catalog/materials")) {
        return {
          ok: true,
          json: async () => ({ materials: [] }),
        };
      }
      if (url.includes("/api/threads") && !url.includes("/messages") && init?.method === "POST") {
        return {
          ok: true,
          json: async () => ({
            thread: {
              thread_id: "thread-1",
              title: "New Thread",
              created_at: "2026-03-08T20:00:00.000Z",
              updated_at: "2026-03-08T20:00:00.000Z",
              message_count: 0,
              last_message_preview: null,
            },
          }),
        };
      }
      if (url.includes("/api/mat/query") && init?.method === "POST") {
        return { ok: false, status: 500, json: async () => ({ detail: "boom" }) };
      }
      return {
        ok: false,
        status: 404,
        json: async () => ({ detail: "Not Found" }),
      };
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    fireEvent.change(screen.getByLabelText("Ask a question"), {
      target: { value: "Question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText(/The backend request failed/)).toBeInTheDocument();
    });
  });
});
