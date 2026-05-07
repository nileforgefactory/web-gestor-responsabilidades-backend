#!/bin/sh
# Espera al daemon Ollama y descarga embeddings + chat locales (primera vez puede tardar mucho).
# Montado en Docker (curlimages/curl). Este archivo debe tener finales de linea LF (Unix).
set -eu

OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
EMBED_MODEL="${EMBED_MODEL:-nomic-embed-text}"
CHAT_MODEL="${CHAT_MODEL:-llama3.2:3b}"
MAX_WAIT="${BOOTSTRAP_MAX_WAIT_SEC:-240}"

wait_for_daemon() {
  i=1
  while [ "$i" -le "${MAX_WAIT}" ]; do
    if curl -sf "${OLLAMA_HOST}/api/tags" >/dev/null; then
      echo "[ollama_pull] Daemon Ollama listo (${OLLAMA_HOST})"
      return 0
    fi
    echo "[ollama_pull] Esperando Ollama... ${i}/${MAX_WAIT}"
    sleep 1
    i=$((i + 1))
  done
  echo "[ollama_pull] ERROR: Ollama no respondio tras ${MAX_WAIT}s" >&2
  exit 1
}

pull_model() {
  name="$1"
  echo "[ollama_pull] Descargando modelo: ${name} (primera vez puede tardar)."
  curl -fsS \
    --connect-timeout 10 \
    --max-time 7200 \
    -X POST "${OLLAMA_HOST}/api/pull" \
    -H "Content-Type: application/json" \
    --data-binary "{\"name\":\"${name}\"}" \
    -o /dev/null
  echo "[ollama_pull] Modelo instalado en el daemon: ${name}"
}

wait_for_daemon
pull_model "${EMBED_MODEL}"
pull_model "${CHAT_MODEL}"
echo "[ollama_pull] Bootstrap completado."
