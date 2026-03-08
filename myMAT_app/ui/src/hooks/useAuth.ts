import { useMemo, useState } from "react";

import {
  clearCurrentUser,
  getCurrentUser,
  getUsers,
  hashPassword,
  saveUsers,
  setCurrentUser,
} from "../services/storage";

export interface AuthResult {
  ok: boolean;
  message: string;
}

export function useAuth() {
  const [currentUser, setCurrentUserState] = useState<string | null>(getCurrentUser);

  const users = useMemo(() => getUsers(), [currentUser]);

  async function register(usernameInput: string, passwordInput: string): Promise<AuthResult> {
    const username = usernameInput.trim();
    const password = passwordInput.trim();

    if (!username || !password) {
      return { ok: false, message: "Username and password are required." };
    }

    if (users.some((user) => user.username.toLowerCase() === username.toLowerCase())) {
      return { ok: false, message: "Username already exists." };
    }

    const passwordHash = await hashPassword(password);
    const updatedUsers = [...users, { username, passwordHash }];
    saveUsers(updatedUsers);
    setCurrentUser(username);
    setCurrentUserState(username);
    return { ok: true, message: "User registered and logged in." };
  }

  async function login(usernameInput: string, passwordInput: string): Promise<AuthResult> {
    const username = usernameInput.trim();
    const password = passwordInput.trim();

    if (!username || !password) {
      return { ok: false, message: "Username and password are required." };
    }

    const found = users.find((user) => user.username.toLowerCase() === username.toLowerCase());
    if (!found) {
      return { ok: false, message: "Invalid username or password." };
    }

    const passwordHash = await hashPassword(password);
    if (found.passwordHash !== passwordHash) {
      return { ok: false, message: "Invalid username or password." };
    }

    setCurrentUser(found.username);
    setCurrentUserState(found.username);
    return { ok: true, message: "Logged in." };
  }

  function logout(): void {
    clearCurrentUser();
    setCurrentUserState(null);
  }

  return {
    currentUser,
    register,
    login,
    logout,
  };
}
