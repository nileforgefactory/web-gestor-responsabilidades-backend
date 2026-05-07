from typing import Any

import httpx


class OllamaError(RuntimeError):
    pass


async def ollama_embed(
    *,
    http: httpx.AsyncClient,
    base_url: str,
    model: str,
    prompt: str,
) -> list[float]:
    url = base_url.rstrip("/") + "/api/embeddings"
    response = await http.post(url, json={"model": model, "prompt": prompt})
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    embedding = payload.get("embedding")
    if not isinstance(embedding, list) or not embedding:
        raise OllamaError(f"Embedding vacío respuesta={payload!r}")
    return [float(x) for x in embedding]


async def ollama_chat(
    *,
    http: httpx.AsyncClient,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
) -> str:
    url = base_url.rstrip("/") + "/api/chat"
    response = await http.post(
        url,
        json={"model": model, "messages": messages, "stream": False},
        timeout=httpx.Timeout(300.0),
    )
    response.raise_for_status()
    payload: dict[str, Any] = response.json()
    msg = payload.get("message") or {}
    content = msg.get("content") if isinstance(msg, dict) else None
    if not content or not isinstance(content, str):
        raise OllamaError(f"Respuesta chat inválida: {payload!r}")
    return content.strip()


async def ollama_health(http: httpx.AsyncClient, base_url: str) -> bool:
    url = base_url.rstrip("/") + "/api/tags"
    response = await http.get(url)
    response.raise_for_status()
    data = response.json()
    return isinstance(data, dict) and "models" in data
