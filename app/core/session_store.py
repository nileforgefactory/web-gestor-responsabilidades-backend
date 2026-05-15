"""
Broker de sesiones para análisis SSE con Redis.
Permite reconexión y replay de eventos históricos.
"""
from __future__ import annotations

import json
import logging
from uuid import uuid4

logger = logging.getLogger(__name__)

_store: "SessionStore | None" = None


class SessionStore:
    TTL = 3600  # 1 hora

    def __init__(self, redis_url: str) -> None:
        import redis.asyncio as aioredis  # importación diferida — falla claro si no instalado
        self.redis = aioredis.from_url(redis_url, decode_responses=True)

    async def create_session(self, plan_id: str, meta: dict | None = None) -> str:
        session_id = str(uuid4())
        payload = {"plan_id": plan_id, "status": "running", "events": []}
        if meta:
            payload.update(meta)
        await self.redis.setex(f"analysis:{session_id}", self.TTL, json.dumps(payload))
        return session_id

    async def append_event(self, session_id: str, event: dict) -> None:
        key = f"analysis:{session_id}"
        raw = await self.redis.get(key)
        data: dict = json.loads(raw) if raw else {"events": []}
        data.setdefault("events", []).append(event)
        await self.redis.setex(key, self.TTL, json.dumps(data))
        await self.redis.publish(f"analysis_channel:{session_id}", json.dumps(event))

    async def get_session(self, session_id: str) -> dict | None:
        raw = await self.redis.get(f"analysis:{session_id}")
        return json.loads(raw) if raw else None

    async def mark_done(self, session_id: str) -> None:
        key = f"analysis:{session_id}"
        raw = await self.redis.get(key)
        data: dict = json.loads(raw) if raw else {}
        data["status"] = "done"
        await self.redis.setex(key, self.TTL, json.dumps(data))

    async def close(self) -> None:
        await self.redis.aclose()


def init_session_store(redis_url: str) -> None:
    global _store
    _store = SessionStore(redis_url)
    logger.info("SessionStore inicializado con Redis: %s", redis_url)


def get_session_store() -> SessionStore | None:
    """Retorna None si Redis no está configurado (modo degradado sin replay)."""
    return _store
