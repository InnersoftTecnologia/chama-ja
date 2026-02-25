#!/bin/bash
#
# Deploy do Chama Já para um servidor Rocky Linux (via SSH).
# Uso: ./scripts/deploy-rocky.sh [user@]host
# Exemplo: SSHPASS='sua_senha' ./scripts/deploy-rocky.sh root@10.132.9.184
# Re-deploy (servidor já preparado): SKIP_PREP=1 SSHPASS='...' ./scripts/deploy-rocky.sh root@10.132.9.184
#
# Requer: sshpass (ou use ssh com chave), rsync.
# No servidor: instala dnf, Docker, MariaDB, Python3, sincroniza o projeto e sobe os serviços + Kokoro.
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TARGET="${1:-}"
if [ -z "$TARGET" ]; then
  echo "Uso: $0 user@host"
  echo "Exemplo: $0 root@10.132.9.184"
  exit 1
fi

# Senha (ambiente controlado). Pode ser passada por variável.
SSHPASS_CMD=""
if [ -n "${SSHPASS:-}" ]; then
  export SSHPASS
  SSHPASS_CMD="sshpass -e"
fi

REMOTE_DIR="/opt/chama-ja"
echo "=== Deploy Chama Já -> $TARGET (${REMOTE_DIR}) ==="

# 1) Preparar servidor: pacotes, Docker, MariaDB, usuário DB (pule com SKIP_PREP=1 se já preparou)
if [ "${SKIP_PREP:-0}" != "1" ]; then
  echo "--- Preparando servidor (pacotes, Docker, MariaDB) ---"
  $SSHPASS_CMD ssh -o StrictHostKeyChecking=no "$TARGET" bash -s << 'REMOTE_PREP'
set -e
if command -v dnf &>/dev/null; then
  dnf install -y rsync mariadb-server mariadb git 2>/dev/null || true
  # Python 3.9+ (Rocky 8: module python39; fallback python3)
  if dnf module list -y python39 2>/dev/null | grep -q python39; then
    dnf module enable -y python39 2>/dev/null || true
    dnf install -y python39 python39-pip python39-devel 2>/dev/null || true
  fi
  dnf install -y python3 python3-pip python3-devel 2>/dev/null || true
  if ! command -v docker &>/dev/null; then
    dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo 2>/dev/null || true
    dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || true
  fi
fi
systemctl enable --now mariadb 2>/dev/null || true
systemctl enable --now docker 2>/dev/null || true
mysql -e "CREATE USER IF NOT EXISTS 'mysql'@'localhost' IDENTIFIED BY 'mysql'; GRANT ALL PRIVILEGES ON *.* TO 'mysql'@'localhost' WITH GRANT OPTION; FLUSH PRIVILEGES;" 2>/dev/null || true
REMOTE_PREP
else
  echo "--- Pulando preparação (SKIP_PREP=1) ---"
fi

# 2) Rsync do projeto (exclui venv e cache)
echo "--- Sincronizando projeto ---"
RSYNC_EXCLUDE="--exclude=.venv --exclude=__pycache__ --exclude=.git/ --exclude=.run/*.pid --exclude=.run/*.log --exclude=*.pyc"
if [ -n "${SSHPASS:-}" ]; then
  sshpass -e rsync -avz --delete $RSYNC_EXCLUDE "$REPO_ROOT/" "$TARGET:${REMOTE_DIR}/"
else
  rsync -avz -e "ssh -o StrictHostKeyChecking=no" --delete $RSYNC_EXCLUDE "$REPO_ROOT/" "$TARGET:${REMOTE_DIR}/"
fi

# 3) No servidor: venv, deps, diretórios, Kokoro, Edge, migrate, seed, start
echo "--- Instalando app e subindo serviços ---"
$SSHPASS_CMD ssh -o StrictHostKeyChecking=no "$TARGET" "REMOTE_DIR=${REMOTE_DIR}" bash -s << 'REMOTE_DEPLOY'
set -e
cd "${REMOTE_DIR:-/opt/chama-ja}"
mkdir -p .run/prints .run/slides .run/slides/thumbs
# Prefer Python 3.9+ se disponível (Rocky 8)
PYTHON_CMD=python3
command -v python3.9 &>/dev/null && PYTHON_CMD=python3.9 || true
command -v python3.11 &>/dev/null && PYTHON_CMD=python3.11 || true
if [ ! -f .venv/bin/activate ]; then
  $PYTHON_CMD -m venv .venv
fi
. .venv/bin/activate
pip install -q -r requirements.txt
# Kokoro: usar standalone se existir, senão só kokoro-api do compose principal
if [ -f kokoro/docker-compose.standalone.yml ]; then
  (cd kokoro && docker compose -f docker-compose.standalone.yml up -d)
else
  (cd kokoro && docker compose up -d kokoro-api)
fi
# Aguardar Kokoro (opcional, pode demorar)
for i in 1 2 3 4 5 6 7 8 9 10; do
  curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 2 http://localhost:8880/health 2>/dev/null | grep -q 200 && break
  sleep 3
done
export DB_HOST=localhost DB_PORT=3306 DB_USER=mysql DB_PASSWORD=mysql DB_NAME=chamador
export EDGE_HOST=0.0.0.0 EDGE_PORT=7071 EDGE_DEVICE_TOKEN=dev-edge-token
export KOKORO_PORT=8880 KOKORO_TTS_URL=http://localhost:8880/v1/audio/speech
export KOKORO_DIR="${REMOTE_DIR:-/opt/chama-ja}/kokoro"
./gerenciar.sh start
sleep 5
# Migrations e seed (token do gerenciar)
curl -sS -X POST "http://localhost:7071/admin/migrate?reset=0" -H "Authorization: Bearer dev-edge-token" || true
curl -sS -X POST "http://localhost:7071/admin/seed" -H "Authorization: Bearer dev-edge-token" || true
echo ""
echo "=== Chama Ja rodando ==="
echo "  Dashboard: http://<IP>:7077"
echo "  Edge API:  http://<IP>:7071"
echo "  TV:        http://<IP>:7073"
echo "  Operador:  http://<IP>:7074"
echo "  Admin:     http://<IP>:7075"
echo "  Totem:     http://<IP>:7076"
echo "  Kokoro:    http://<IP>:8880"
REMOTE_DEPLOY

echo ""
echo "Deploy concluído. Acesse http://10.132.9.184:7077 (ou o IP do servidor)."
