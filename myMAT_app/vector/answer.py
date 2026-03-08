from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage, convert_to_messages
from langchain_openai import ChatOpenAI

from .config import (
    DEFAULT_CHAT_MODEL,
    DEFAULT_COLLECTION_NAME,
    DEFAULT_DB_PATH,
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_RETRIEVAL_FETCH_K,
    DEFAULT_RETRIEVAL_K,
    DEFAULT_RETRIEVAL_LAMBDA_MULT,
    DEFAULT_RETRIEVAL_SEARCH_TYPE,
    OLLAMA_CHAT_MODELS,
)
from .retrieval import retrieve_context

SYSTEM_PROMPT = """
You are a knowledgeable assistant for myMAT knowledge.
Use only the retrieved context as evidence.
If context is partially relevant, provide the best possible answer and clearly label uncertainty.
If context is truly insufficient, say: "I do not know based on the provided documents."
Include short source citations using [source_name] or [source_name p.X] when possible.
Context:
{context}
""".strip()

STRUCTURED_SYSTEM_PROMPT = """
You are a knowledgeable assistant for myMAT knowledge.
Use only retrieved context as evidence.
Return ONLY JSON object with this schema:
{{
  "bullets": ["point 1", "point 2", "point 3"],
  "answer_text": "short paragraph answer"
}}
Rules:
- Provide 3 to 5 concise bullets.
- Each bullet must be factual and grounded in context.
- If context is insufficient, include one bullet that states uncertainty clearly.
- Do not output markdown fences.
Context:
{context}
""".strip()


@dataclass(slots=True)
class StructuredRagAnswer:
    prompt: str
    bullets: list[str]
    answer_text: str


def _create_chat_model(model_name: str):
    if model_name in OLLAMA_CHAT_MODELS:
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError(
                "Model selection requires langchain-ollama for Ollama models. "
                "Install with: uv pip install --python .venv/bin/python langchain-ollama"
            ) from exc
        ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        return ChatOllama(model=model_name, base_url=ollama_url, temperature=0)

    return ChatOpenAI(model_name=model_name, temperature=0)


def _combined_query(question: str, history: list[dict] | None) -> str:
    if not history:
        return question
    prior_questions = [m.get("content", "") for m in history if m.get("role") == "user"]
    return "\n".join([*prior_questions, question]).strip()


def _format_context(docs: list[Document]) -> str:
    if not docs:
        return "(no retrieved context)"

    parts: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        source_name = doc.metadata.get("source_name", "unknown")
        doc_type = doc.metadata.get("doc_type", "unknown")
        page = doc.metadata.get("page_number")
        sheet = doc.metadata.get("sheet_name")

        locator = []
        if page:
            locator.append(f"page={page}")
        if sheet:
            locator.append(f"sheet={sheet}")
        locator_text = f" ({', '.join(locator)})" if locator else ""

        parts.append(
            f"[{idx}] source={source_name} doc_type={doc_type}{locator_text}\n{doc.page_content}"
        )
    return "\n\n---\n\n".join(parts)


def _retrieve_docs_and_context(
    question: str,
    history: list[dict] | None,
    *,
    db_path: Path,
    collection_name: str,
    embedding_model: str,
    k: int,
    search_type: str,
    fetch_k: int,
    lambda_mult: float,
    doc_type: str | None,
    source_contains: str | None,
) -> tuple[list[Document], str]:
    query = _combined_query(question, history)
    docs = retrieve_context(
        query,
        db_path=db_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
        k=k,
        search_type=search_type,
        fetch_k=fetch_k,
        lambda_mult=lambda_mult,
        doc_type=doc_type,
        source_contains=source_contains,
    )
    context = _format_context(docs)
    return docs, context


def _clean_json_text(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _strip_reasoning_traces(raw: str) -> str:
    # Qwen-style reasoning often appears inside <think>...</think>.
    text = re.sub(r"<think>.*?</think>", " ", raw, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"</?think>", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _extract_json_object(raw: str) -> dict | None:
    cleaned = _clean_json_text(raw)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(cleaned[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


def _fallback_bullets(text: str, max_items: int = 4) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return ["I do not know based on the provided documents."]

    sentence_parts = re.split(r"(?<=[.!?])\s+", normalized)
    bullets: list[str] = []
    for sentence in sentence_parts:
        clean = sentence.strip(" -")
        if len(clean) >= 12:
            bullets.append(clean)
        if len(bullets) >= max_items:
            break

    if not bullets:
        bullets = [normalized]
    return bullets


def _parse_structured_answer(raw_text: str, question: str) -> StructuredRagAnswer:
    sanitized_text = _strip_reasoning_traces(raw_text)
    data = _extract_json_object(sanitized_text)
    if not isinstance(data, dict):
        bullets = _fallback_bullets(sanitized_text)
        return StructuredRagAnswer(
            prompt=question,
            bullets=bullets,
            answer_text=sanitized_text.strip(),
        )

    raw_bullets = data.get("bullets", [])
    raw_answer_text = data.get("answer_text", "")

    bullets: list[str] = []
    if isinstance(raw_bullets, list):
        for item in raw_bullets:
            if not isinstance(item, str):
                continue
            bullet = _strip_reasoning_traces(str(item)).strip(" -")
            if bullet and bullet not in bullets:
                bullets.append(bullet)
            if len(bullets) >= 5:
                break

    answer_text = _strip_reasoning_traces(str(raw_answer_text))
    if not bullets:
        bullets = _fallback_bullets(answer_text or sanitized_text)
    if not answer_text:
        answer_text = " ".join(bullets[:2]).strip()
    # Extra safety: never return reasoning traces or embedded JSON scaffolding as final text.
    if "<think>" in answer_text.lower() or '"bullets"' in answer_text.lower() or '"answer_text"' in answer_text.lower():
        answer_text = " ".join(bullets[:2]).strip()

    return StructuredRagAnswer(prompt=question, bullets=bullets[:5], answer_text=answer_text)


def _format_legacy_answer(structured: StructuredRagAnswer) -> str:
    bullet_lines = [f"- {bullet}" for bullet in structured.bullets]
    parts = bullet_lines
    if structured.answer_text:
        parts.append("")
        parts.append(structured.answer_text)
    return "\n".join(parts).strip()


def answer_question(
    question: str,
    history: list[dict] | None = None,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chat_model: str = DEFAULT_CHAT_MODEL,
    k: int = DEFAULT_RETRIEVAL_K,
    search_type: str = DEFAULT_RETRIEVAL_SEARCH_TYPE,
    fetch_k: int = DEFAULT_RETRIEVAL_FETCH_K,
    lambda_mult: float = DEFAULT_RETRIEVAL_LAMBDA_MULT,
    doc_type: str | None = None,
    source_contains: str | None = None,
) -> tuple[str, list[Document]]:
    load_dotenv(override=True)
    docs, context = _retrieve_docs_and_context(
        question,
        history,
        db_path=db_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
        k=k,
        search_type=search_type,
        fetch_k=fetch_k,
        lambda_mult=lambda_mult,
        doc_type=doc_type,
        source_contains=source_contains,
    )
    llm = _create_chat_model(chat_model)

    messages = [SystemMessage(content=SYSTEM_PROMPT.format(context=context))]
    if history:
        messages.extend(convert_to_messages(history))
    messages.append(HumanMessage(content=question))
    response = llm.invoke(messages)
    return str(response.content), docs


def answer_question_structured(
    question: str,
    history: list[dict] | None = None,
    *,
    db_path: Path = DEFAULT_DB_PATH,
    collection_name: str = DEFAULT_COLLECTION_NAME,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    chat_model: str = DEFAULT_CHAT_MODEL,
    k: int = DEFAULT_RETRIEVAL_K,
    search_type: str = DEFAULT_RETRIEVAL_SEARCH_TYPE,
    fetch_k: int = DEFAULT_RETRIEVAL_FETCH_K,
    lambda_mult: float = DEFAULT_RETRIEVAL_LAMBDA_MULT,
    doc_type: str | None = None,
    source_contains: str | None = None,
) -> tuple[StructuredRagAnswer, str, list[Document]]:
    load_dotenv(override=True)
    docs, context = _retrieve_docs_and_context(
        question,
        history,
        db_path=db_path,
        collection_name=collection_name,
        embedding_model=embedding_model,
        k=k,
        search_type=search_type,
        fetch_k=fetch_k,
        lambda_mult=lambda_mult,
        doc_type=doc_type,
        source_contains=source_contains,
    )
    llm = _create_chat_model(chat_model)
    messages = [SystemMessage(content=STRUCTURED_SYSTEM_PROMPT.format(context=context))]
    if history:
        messages.extend(convert_to_messages(history))
    messages.append(HumanMessage(content=question))
    response = llm.invoke(messages)
    raw_text = str(response.content)
    structured = _parse_structured_answer(raw_text, question=question)
    legacy_answer = _format_legacy_answer(structured)
    return structured, legacy_answer, docs
