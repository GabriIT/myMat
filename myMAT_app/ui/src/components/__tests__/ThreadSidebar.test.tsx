import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import type { ChatThread } from "../../types";
import { ThreadSidebar } from "../ThreadSidebar";

function makeThread(id: string, title: string, updatedAt: string): ChatThread {
  return {
    id,
    title,
    createdAt: updatedAt,
    updatedAt,
    messages: [],
  };
}

describe("ThreadSidebar", () => {
  it("sorts threads by updatedAt and supports select/new", () => {
    const onSelect = vi.fn();
    const onCreate = vi.fn();
    const onRename = vi.fn();
    const onDelete = vi.fn();

    render(
      <ThreadSidebar
        username="alice"
        threads={[
          makeThread("old", "Older", "2026-01-01T10:00:00.000Z"),
          makeThread("new", "Newest", "2026-03-01T12:00:00.000Z"),
        ]}
        activeThreadId={"new"}
        mobileOpen={false}
        onToggleMobile={vi.fn()}
        onCreateThread={onCreate}
        onSelectThread={onSelect}
        onRenameThread={onRename}
        onDeleteThread={onDelete}
        onLogout={vi.fn()}
      />,
    );

    const titles = screen.getAllByRole("button", { name: /Newest|Older/ }).map((el) => el.textContent);
    expect(titles[0]).toContain("Newest");
    expect(titles[1]).toContain("Older");

    fireEvent.click(screen.getByRole("button", { name: /\+ New Thread/ }));
    expect(onCreate).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Older/ }));
    expect(onSelect).toHaveBeenCalledWith("old");

    fireEvent.click(screen.getByRole("button", { name: "Selected Thread Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Rename" }));
    expect(onRename).toHaveBeenCalledWith("new", "Newest");

    fireEvent.click(screen.getByRole("button", { name: "Selected Thread Actions" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(onDelete).toHaveBeenCalledWith("new");
  });
});
