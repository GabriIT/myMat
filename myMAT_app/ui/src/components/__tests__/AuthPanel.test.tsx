import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { AuthPanel } from "../AuthPanel";

describe("AuthPanel", () => {
  it("submits register mode and shows message", async () => {
    const onRegister = vi.fn(async () => ({ ok: true, message: "registered" }));
    const onLogin = vi.fn(async () => ({ ok: true, message: "logged" }));

    render(<AuthPanel onRegister={onRegister} onLogin={onLogin} />);

    fireEvent.click(screen.getByRole("tab", { name: "Register" }));
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "alice" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));

    expect(onRegister).toHaveBeenCalledWith("alice", "secret");
    expect(await screen.findByText("registered")).toBeInTheDocument();
  });

  it("submits login mode and shows failure", async () => {
    const onRegister = vi.fn(async () => ({ ok: true, message: "registered" }));
    const onLogin = vi.fn(async () => ({ ok: false, message: "Invalid username or password." }));

    render(<AuthPanel onRegister={onRegister} onLogin={onLogin} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Login" }));

    expect(onLogin).toHaveBeenCalledWith("bob", "bad");
    expect(await screen.findByText("Invalid username or password.")).toBeInTheDocument();
  });
});
