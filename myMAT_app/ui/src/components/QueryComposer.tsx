import { FormEvent, useState } from "react";
import type { ChatModelOption } from "../types";

const CHAT_MODEL_OPTIONS: Array<{ value: ChatModelOption; label: string }> = [
  { value: "gpt-4.1-nano", label: "Fine-T-LLM (default)" },
  { value: "qwen3.5:9b", label: "qwen3.5:9b (Ollama)" },
  { value: "llama3.2:latest", label: "llama3.2:latest (Ollama)" },
];

interface QueryComposerProps {
  disabled: boolean;
  isSending: boolean;
  selectedModel: ChatModelOption;
  allowEmptySend?: boolean;
  placeholder?: string;
  onSelectModel: (model: ChatModelOption) => void;
  onSend: (query: string, model: ChatModelOption) => Promise<void>;
}

export function QueryComposer({
  disabled,
  isSending,
  selectedModel,
  allowEmptySend = false,
  placeholder = "Your Query - Your Project Description - We provide your solution!",
  onSelectModel,
  onSend,
}: QueryComposerProps) {
  const [query, setQuery] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmed = query.trim();
    if ((!trimmed && !allowEmptySend) || disabled || isSending) {
      return;
    }
    if (trimmed) {
      setQuery("");
    }
    await onSend(trimmed, selectedModel);
  }

  return (
    <form className="query-composer" onSubmit={handleSubmit}>
      <div className="query-input-wrap">
        <label className="query-model">
          <span>Model</span>
          <select
            aria-label="Chat model"
            value={selectedModel}
            onChange={(event) => onSelectModel(event.target.value as ChatModelOption)}
            disabled={disabled || isSending}
          >
            {CHAT_MODEL_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <input
          aria-label="Ask a question"
          placeholder={placeholder}
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          disabled={disabled || isSending}
        />
      </div>
      <button type="submit" disabled={disabled || isSending || (!allowEmptySend && !query.trim())}>
        {isSending ? "Sending..." : "Send"}
      </button>
    </form>
  );
}
