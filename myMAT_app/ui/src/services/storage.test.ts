import {
  getActiveThreadId,
  getUsers,
  hashPassword,
  saveUsers,
  setActiveThreadId,
} from "./storage";

describe("storage service", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("stores active thread pointer per user", () => {
    setActiveThreadId("alice", "thread-a");
    setActiveThreadId("bob", "thread-b");
    expect(getActiveThreadId("alice")).toBe("thread-a");
    expect(getActiveThreadId("bob")).toBe("thread-b");
  });

  it("persists and reads users", () => {
    saveUsers([{ username: "alice", passwordHash: "h" }]);
    expect(getUsers()).toEqual([{ username: "alice", passwordHash: "h" }]);
  });

  it("falls back when crypto.subtle is unavailable", async () => {
    const originalCrypto = globalThis.crypto;
    Object.defineProperty(globalThis, "crypto", { value: undefined, configurable: true });
    try {
      const one = await hashPassword("secret");
      const two = await hashPassword("secret");
      expect(one).toBe(two);
      expect(one.startsWith("fallback-")).toBe(true);
    } finally {
      Object.defineProperty(globalThis, "crypto", { value: originalCrypto, configurable: true });
    }
  });
});
