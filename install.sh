#!/bin/bash
#
# Script de instalação do Chama Já
# Uso:
#   ./install.sh [DIRETÓRIO]
# Se DIRETÓRIO for omitido, usa o diretório atual.
# Se o diretório não for um clone do repositório, faz clone de
# https://github.com/InnersoftTecnologia/chama-ja e depois configura.
#
set -euo pipefail

REPO_URL="https://github.com/InnersoftTecnologia/chama-ja.git"
INSTALL_DIR="${1:-.}"

if [ -n "${1:-}" ]; then
  mkdir -p "$INSTALL_DIR"
  INSTALL_DIR="$(cd "$INSTALL_DIR" && pwd)"
fi

# --- Determinar raiz do projeto (já é clone ou clonar)
if [ -f "${INSTALL_DIR}/requirements.txt" ] && [ -d "${INSTALL_DIR}/.git" ]; then
  ROOT="$(cd "$INSTALL_DIR" && pwd)"
  cd "$ROOT"
else
  if [ "$INSTALL_DIR" = "." ] || [ -z "${1:-}" ]; then
    if [ -f "requirements.txt" ] && [ -d ".git" ]; then
      ROOT="$(pwd)"
      cd "$ROOT"
    else
      echo "Clonando repositório em ./chama-ja ..."
      git clone "$REPO_URL" chama-ja
      cd chama-ja
      ROOT="$(pwd)"
    fi
  else
    if [ -d "$INSTALL_DIR" ] && [ "$(ls -A "$INSTALL_DIR" 2>/dev/null)" ]; then
      echo "Diretório $INSTALL_DIR já existe e não está vazio. Use um diretório vazio ou omita para usar o atual."
      exit 1
    fi
    mkdir -p "$INSTALL_DIR"
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    ROOT="$(pwd)"
  fi
fi

if [ ! -f "$ROOT/requirements.txt" ]; then
  echo "Não foi possível encontrar o projeto (requirements.txt). Abortando."
  exit 1
fi

echo "Raiz do projeto: $ROOT"

# --- Estrutura de diretórios
mkdir -p "$ROOT/.run/prints"
mkdir -p "$ROOT/.run/slides"
mkdir -p "$ROOT/.run/slides/thumbs"
echo "Diretórios .run criados."

# --- Venv e dependências
if [ ! -f "$ROOT/.venv/bin/activate" ]; then
  echo "Criando ambiente virtual em .venv ..."
  python3 -m venv "$ROOT/.venv"
fi
echo "Ativando .venv e instalando dependências ..."
# shellcheck disable=SC1090
. "$ROOT/.venv/bin/activate"
pip install -q -r "$ROOT/requirements.txt"
echo "Dependências instaladas."

# --- Hooks de Git (versão automática)
if [ -d "$ROOT/.git" ] && [ -d "$ROOT/githooks" ]; then
  if [ -x "$ROOT/scripts/setup-git-hooks.sh" ]; then
    "$ROOT/scripts/setup-git-hooks.sh"
  elif [ -d "$ROOT/githooks" ]; then
    for f in "$ROOT/githooks"/*; do
      [ -f "$f" ] || continue
      name="$(basename "$f")"
      cp "$f" "$ROOT/.git/hooks/$name"
      chmod +x "$ROOT/.git/hooks/$name"
      echo "Hook instalado: $name"
    done
  fi
fi

# --- .env (opcional)
if [ ! -f "$ROOT/.env" ] && [ -f "$ROOT/.env.example" ]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
  echo "Arquivo .env criado a partir de .env.example. Ajuste se necessário."
fi

echo ""
echo "Instalação concluída."
echo "  cd $ROOT"
echo "  source .venv/bin/activate   # se ainda não estiver ativo"
echo "  ./gerenciar.sh start         # sobe Edge, TV, Operador, Admin, Totem"
echo "  # Migrations e seed: curl -X POST 'http://localhost:7071/admin/migrate?reset=0' -H 'Authorization: Bearer dev-edge-token'"
echo "  #                      curl -X POST http://localhost:7071/admin/seed -H 'Authorization: Bearer dev-edge-token'"
