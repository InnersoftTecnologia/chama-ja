#!/usr/bin/env bash
# Força reinício do Edge (API) para carregar novo código (ex.: formato do ticket).
# Uso: ./scripts/reiniciar-edge.sh

set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
EDGE_PID_FILE="${ROOT}/.run/chama_ja_edge.pid"

echo "Parando Edge..."
if [ -f "$EDGE_PID_FILE" ]; then
  PID=$(cat "$EDGE_PID_FILE")
  kill -9 -$PID 2>/dev/null || kill -9 $PID 2>/dev/null || true
  rm -f "$EDGE_PID_FILE"
fi
for p in $(lsof -t -i:7071 2>/dev/null); do
  echo "  Matando processo $p na porta 7071"
  kill -9 $p 2>/dev/null || true
done
sleep 2
echo "Iniciando Edge..."
./gerenciar.sh start
echo "Pronto. Emita um ticket no totem para testar o novo formato (sem código de barras)."
