import json
import os
import sys
import time
import urllib.error
import urllib.request


def ping(url: str, timeout: float = 10) -> None:
    with urllib.request.urlopen(url, timeout=timeout):
        pass


def wait_for(name: str, url: str, attempts: int) -> None:
    last: BaseException | None = None
    for i in range(attempts):
        try:
            ping(url)
            print(f"[wait_services] OK: {name} ({url})", flush=True)
            return
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            last = exc
            if i % 10 == 0:
                print(
                    f"[wait_services] Esperando {name}... intento={i + 1} error={exc!r}",
                    flush=True,
                )
            time.sleep(1)
    print(f"[wait_services] Timeout esperando {name}: {last!r}", file=sys.stderr, flush=True)
    raise SystemExit(1)


def _parse_models(payload: dict[str, object]) -> list[str]:
    out: list[str] = []
    raw = payload.get("models") or []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        n = row.get("name")
        if isinstance(n, str):
            out.append(n)
    return out


def _model_registered(installed_names: list[str], want: str) -> bool:
    want_base = want.split(":")[0].strip().lower()
    want_full = want.strip().lower()
    for raw in installed_names:
        cand = raw.strip().lower()
        cand_base = cand.split(":")[0]
        if cand == want_full or cand_base == want_base:
            return True
        if cand.startswith(want_base + ":"):
            return True
    return False


def _verify_registry(base_url: str) -> tuple[bool, list[str], str]:
    embed = os.getenv("OLLAMA_EMBEDDING_MODEL", "nomic-embed-text").strip()
    chat = os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:3b").strip()
    tags_url = base_url.rstrip("/") + "/api/tags"
    with urllib.request.urlopen(tags_url, timeout=30) as r:
        payload = json.load(r)
    if not isinstance(payload, dict):
        return False, [], "payload /api/tags inesperado"
    installed = _parse_models(payload)
    eb = _model_registered(installed, embed)
    cb = _model_registered(installed, chat)
    if eb and cb:
        return True, installed, ""

    missing: list[str] = []
    if not eb:
        missing.append(embed)
    if not cb:
        missing.append(chat)
    return False, installed, ", ".join(missing)


def _wait_registered_models(base_url: str) -> None:
    """Tras docker ollama-pull los modelos deberían existir; reintenta ante carreras o cold start."""
    for i in range(120):
        ok, installed, missing = _verify_registry(base_url)
        if ok:
            print("[wait_services] Modelos en Ollama verificados (registry)", flush=True)
            return

        visible = installed[:15]
        suffix = ""
        if len(installed) > 15:
            suffix = ", ..."

        if i % 8 == 0:
            print(
                f"[wait_services] Esperando registrar modelos: faltan {missing!r}. "
                f"Known={visible}{suffix} (intento {i + 1}/120)",
                flush=True,
            )
        time.sleep(3)

    ok, _, missing = _verify_registry(base_url)
    if not ok:
        print(
            "[wait_services] ERROR: tras arranque siguen ausentes estos modelos: "
            f"{missing!r}. Revisa logs del servicio ollama-pull.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(1)


def main() -> None:
    qdr = os.getenv("QDRANT_URL")
    if not qdr:
        print("[wait_services] QDRANT_URL no definido", file=sys.stderr, flush=True)
        raise SystemExit(1)

    collections_url = qdr.rstrip("/") + "/collections"
    wait_for("qdrant", collections_url, attempts=240)

    use_ollama = os.getenv("USE_OLLAMA", "true").lower() != "false"
    if use_ollama:
        ol = os.getenv("OLLAMA_BASE_URL")
        if not ol:
            print("[wait_services] OLLAMA_BASE_URL no definido", file=sys.stderr, flush=True)
            raise SystemExit(1)
        tags_url = ol.rstrip("/") + "/api/tags"
        wait_for("ollama", tags_url, attempts=480)
        _wait_registered_models(ol)


if __name__ == "__main__":
    main()
