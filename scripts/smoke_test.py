#!/usr/bin/env python3
"""Prueba de humo: health/ready → ingesta TXT → ask con chunks usados."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("API_BASE_URL", "http://localhost:8000").rstrip("/")
COLLECTION = os.getenv("SMOKE_COLLECTION_ID", "smoke_test")
DOC_ID = "smoke_doc"


def _get(path: str, *, accept_503: bool = False) -> tuple[int, dict]:
    req = urllib.request.Request(f"{BASE}{path}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode()
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {"raw": body}
        if accept_503 and exc.code == 503:
            return exc.code, data
        raise


def _post_json(path: str, payload: dict, *, timeout: float = 300) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main() -> int:
    print(f"[smoke] API_BASE_URL={BASE}")

    status, ready = _get("/health/ready", accept_503=True)
    if status != 200 or not ready.get("healthy"):
        print("[smoke] FALLO: /health/ready no está healthy", file=sys.stderr)
        print(json.dumps(ready, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print("[smoke] OK health/ready")

    ingest_body = {
        "collection_id": COLLECTION,
        "document_id": DOC_ID,
        "content": (
            "Política de incidentes P1: primera respuesta en 15 minutos. "
            "Escalamiento al equipo de guardia en menos de 1 hora."
        ),
        "chunk_size": 400,
        "chunk_overlap": 80,
    }
    ing = _post_json("/api/v1/rag/ingest-text", ingest_body, timeout=120)
    if ing.get("chunks_indexed", 0) < 1:
        print("[smoke] FALLO: ingest-text sin chunks", file=sys.stderr)
        return 1
    print(f"[smoke] OK ingest-text chunks={ing['chunks_indexed']}")

    ask_body = {
        "collection_ids": [COLLECTION],
        "user_message": "¿Cuál es el SLA de primera respuesta para un incidente P1?",
        "top_k": 5,
    }
    ans = _post_json("/api/v1/rag/ask", ask_body, timeout=600)
    used = ans.get("used_chunks") or []
    if not used:
        print("[smoke] FALLO: ask sin used_chunks", file=sys.stderr)
        print(json.dumps(ans, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(f"[smoke] OK ask used_chunks={len(used)}")
    print("[smoke] Prueba de humo completada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
