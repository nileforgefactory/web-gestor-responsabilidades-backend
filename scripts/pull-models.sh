#!/usr/bin/env sh
# Finales de linea LF (Unix). CRLF desde Windows puede romper "set -eu".
set -eu

docker compose exec ollama ollama pull nomic-embed-text
docker compose exec ollama ollama pull llama3.2:3b
