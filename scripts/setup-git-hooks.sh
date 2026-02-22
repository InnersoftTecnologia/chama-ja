#!/bin/bash
# Copia os hooks de githooks/ para .git/hooks e torna executáveis.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${ROOT}/githooks"
DST="${ROOT}/.git/hooks"
if [ ! -d "$SRC" ]; then
  echo "Pasta githooks/ não encontrada."
  exit 1
fi
if [ ! -d "$DST" ]; then
  echo "Pasta .git/hooks não encontrada. Execute dentro de um repositório git."
  exit 1
fi
for f in "$SRC"/*; do
  [ -f "$f" ] || continue
  name="$(basename "$f")"
  cp "$f" "${DST}/${name}"
  chmod +x "${DST}/${name}"
  echo "Hook instalado: ${name}"
done
echo "Hooks configurados. A cada commit o .version será incrementado automaticamente."
