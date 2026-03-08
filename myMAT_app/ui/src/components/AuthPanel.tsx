import { FormEvent, useState } from "react";

import type { AuthResult } from "../hooks/useAuth";

interface AuthPanelProps {
  onRegister: (username: string, password: string) => Promise<AuthResult>;
  onLogin: (username: string, password: string) => Promise<AuthResult>;
}

export function AuthPanel({ onRegister, onLogin }: AuthPanelProps) {
  const [mode, setMode] = useState<"register" | "login">("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) {
      return;
    }

    setBusy(true);
    setFeedback(null);

    try {
      const action = mode === "register" ? onRegister : onLogin;
      const result = await action(username, password);
      setFeedback(result.message);

      if (!result.ok) {
        return;
      }

      setUsername("");
      setPassword("");
    } catch {
      setFeedback("Authentication failed unexpectedly. Please retry.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <h1>myMAT Workspace</h1>
        <p>Register or login to access your local thread history.</p>

        <div className="auth-tabs" role="tablist" aria-label="Auth mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            className={mode === "login" ? "active" : ""}
            onClick={() => setMode("login")}
          >
            Login
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            className={mode === "register" ? "active" : ""}
            onClick={() => setMode("register")}
          >
            Register
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          <label>
            Username
            <input
              name="username"
              value={username}
              onChange={(event) => setUsername(event.target.value)}
              autoComplete="username"
              placeholder="username"
            />
          </label>

          <label>
            Password
            <input
              name="password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              placeholder="password"
            />
          </label>

          <button type="submit" disabled={busy}>
            {busy ? "Please wait..." : mode === "register" ? "Register" : "Login"}
          </button>
        </form>

        {feedback ? (
          <p className="auth-feedback" role="status">
            {feedback}
          </p>
        ) : null}
      </div>
    </div>
  );
}
