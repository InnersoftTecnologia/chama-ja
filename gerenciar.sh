#!/bin/bash

set -euo pipefail

# --- Configurações (tudo derivado do diretório onde está o script) ---
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Nome do projeto = nome do diretório raiz, com "-" trocado por "_" (para arquivos .run e DB)
PROJECT_NAME="$(basename "$ROOT_DIR" | tr '-' '_')"
RUN_DIR="${ROOT_DIR}/.run"
mkdir -p "$RUN_DIR"

# Portas (escopo 7070–7079)
EDGE_HOST="${EDGE_HOST:-0.0.0.0}"
EDGE_PORT="${EDGE_PORT:-7071}"
DASHBOARD_PORT="${DASHBOARD_PORT:-7077}"
TV_PORT="${TV_PORT:-7073}"
TEST_PORT="${TEST_PORT:-7072}"
ADMIN_PORT="${ADMIN_PORT:-7075}"
OP_PORT="${OP_PORT:-7074}"
TOTEM_PORT="${TOTEM_PORT:-7076}"

EDGE_URL="http://localhost:${EDGE_PORT}"
DASHBOARD_URL="http://localhost:${DASHBOARD_PORT}"
TV_URL="http://localhost:${TV_PORT}"
TEST_URL="http://localhost:${TEST_PORT}"
ADMIN_URL="http://localhost:${ADMIN_PORT}"
OP_URL="http://localhost:${OP_PORT}"
TOTEM_URL="http://localhost:${TOTEM_PORT}"

# DB (MariaDB local; nome do banco independente do nome do projeto)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-mysql}"
DB_PASSWORD="${DB_PASSWORD:-mysql}"
DB_NAME="${DB_NAME:-chamador}"

# Token simples (MVP)
EDGE_DEVICE_TOKEN="${EDGE_DEVICE_TOKEN:-dev-edge-token}"

# IP/host acessível na rede (para QR do Totem no dashboard). Se vazio, a Edge tenta detectar.
PUBLIC_HOST="${PUBLIC_HOST:-}"

# Kokoro TTS (opcional — dependência externa)
# KOKORO_DIR: diretório onde está o docker-compose.yml do Kokoro.
# Pode ser qualquer caminho: /opt/kokoro, /home/kokoro, etc.
# Se vazio, o gerenciar.sh não tenta subir o Kokoro, apenas verifica a porta.
KOKORO_PORT="${KOKORO_PORT:-8880}"
KOKORO_DIR="${KOKORO_DIR:-${ROOT_DIR}/kokoro}"
KOKORO_TTS_URL="${KOKORO_TTS_URL:-http://localhost:${KOKORO_PORT}/v1/audio/speech}"

# PIDs/logs
EDGE_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_edge.pid"
DASHBOARD_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_dashboard.pid"
TV_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_tv.pid"
TEST_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_test.pid"
ADMIN_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_admin.pid"
OP_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_op.pid"
TOTEM_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_totem.pid"

EDGE_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_edge.log"
DASHBOARD_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_dashboard.log"
TV_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_tv.log"
TEST_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_test.log"
ADMIN_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_admin.log"
OP_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_op.log"
TOTEM_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_totem.log"

# Uvicorn tuning (helps avoid "stuck shutting down" with SSE/keep-alive)
EDGE_UVICORN_TIMEOUT_KEEP_ALIVE="${EDGE_UVICORN_TIMEOUT_KEEP_ALIVE:-15}"
EDGE_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN="${EDGE_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-5}"
EDGE_UVICORN_EXTRA_ARGS="${EDGE_UVICORN_EXTRA_ARGS:-}"

# Python para servidores HTTP estáticos (3.7+ para --directory). No Rocky 8 use: PYTHON_HTTP=python3.9
PYTHON_HTTP="${PYTHON_HTTP:-python3}"

# Cores para o output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # Sem Cor

# --- Funções de Gerenciamento ---

ensure_venv() {
    if [ ! -f "${ROOT_DIR}/.venv/bin/activate" ]; then
        echo -e "${RED}ERRO:${NC} venv não encontrado em ${ROOT_DIR}/.venv. Rode:"
        echo "  python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

pid_is_running() {
    local pid_file="$1"
    if [ -f "$pid_file" ]; then
        local pid
        pid="$(cat "$pid_file" 2>/dev/null || true)"
        if [ -n "${pid}" ] && kill -0 "$pid" >/dev/null 2>&1; then
            return 0
        fi
    fi
    return 1
}

port_is_listening() {
    local port="$1"
    ss -ltn "sport = :${port}" 2>/dev/null | grep -q ":${port}"
}

pid_from_port() {
    local port="$1"
    # Best-effort: parse pid from ss output (works when ss can show process info)
    ss -ltnp 2>/dev/null | awk -v p=":${port}" '
        $4 ~ p {
            match($0, /pid=([0-9]+)/, m);
            if (m[1] != "") { print m[1]; exit 0; }
        }
    ' || true
}

# Aguarda a porta ficar em LISTEN (até max_sec segundos). Retorna 0 se ok, 1 se timeout.
wait_for_port() {
    local port="$1"
    local max_sec="${2:-30}"
    local elapsed=0
    while [ "$elapsed" -lt "$max_sec" ]; do
        if port_is_listening "$port"; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
}

wait_for_edge() {
    wait_for_port "$EDGE_PORT" "${1:-30}"
}

# Testa se uma URL responde com HTTP 200 (retorna 0 se ok, 1 se falha).
# Uso: check_http_get "http://localhost:7071/health" [max_tentativas]
check_http_get() {
    local url="$1"
    local max_tries="${2:-5}"
    local code i
    for i in $(seq 1 "$max_tries"); do
        code="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 5 "$url" 2>/dev/null || echo "000")"
        if [ "$code" = "200" ]; then
            return 0
        fi
        [ "$i" -lt "$max_tries" ] && sleep 1
    done
    return 1
}

# Verifica cada serviço com requisição HTTP e imprime OK/FAIL.
verify_all_services() {
    echo -e "\n${BLUE}Verificando funcionalidades (HTTP)...${NC}"
    local failed=0

    if check_http_get "${DASHBOARD_URL}/" 5; then
        echo -e "  Dashboard      ${GREEN}OK${NC}  ${DASHBOARD_URL}"
    else
        echo -e "  Dashboard      ${RED}FALHA${NC}  ${DASHBOARD_URL}"
        failed=$((failed + 1))
    fi

    if check_http_get "${EDGE_URL}/health" 8; then
        echo -e "  Edge (API)     ${GREEN}OK${NC}  ${EDGE_URL}/health"
    else
        echo -e "  Edge (API)     ${RED}FALHA${NC}  ${EDGE_URL}/health (veja $EDGE_LOG_FILE)"
        failed=1
    fi

    if check_http_get "${TV_URL}/" 5; then
        echo -e "  TV             ${GREEN}OK${NC}  ${TV_URL}"
    else
        echo -e "  TV             ${RED}FALHA${NC}  ${TV_URL}"
        failed=$((failed + 1))
    fi

    if check_http_get "${TEST_URL}/" 5; then
        echo -e "  Test UI        ${GREEN}OK${NC}  ${TEST_URL}"
    else
        echo -e "  Test UI        ${RED}FALHA${NC}  ${TEST_URL}"
        failed=$((failed + 1))
    fi

    if check_http_get "${OP_URL}/" 5; then
        echo -e "  Operador       ${GREEN}OK${NC}  ${OP_URL}"
    else
        echo -e "  Operador       ${RED}FALHA${NC}  ${OP_URL}"
        failed=$((failed + 1))
    fi

    if check_http_get "${ADMIN_URL}/" 5; then
        echo -e "  Admin Tenant   ${GREEN}OK${NC}  ${ADMIN_URL}"
    else
        echo -e "  Admin Tenant   ${RED}FALHA${NC}  ${ADMIN_URL}"
        failed=$((failed + 1))
    fi

    if check_http_get "${TOTEM_URL}/" 5; then
        echo -e "  Totem          ${GREEN}OK${NC}  ${TOTEM_URL}"
    else
        echo -e "  Totem          ${RED}FALHA${NC}  ${TOTEM_URL}"
        failed=$((failed + 1))
    fi

    # Kokoro TTS: opcional — falha silenciosa, só avisa
    if kokoro_is_up; then
        echo -e "  Kokoro TTS     ${GREEN}OK${NC}  http://localhost:${KOKORO_PORT}"
    else
        echo -e "  Kokoro TTS     ${YELLOW}INATIVO${NC}  http://localhost:${KOKORO_PORT}  (TTS desativado — use 'kokoro start' para subir)"
    fi

    if [ "$failed" -gt 0 ]; then
        echo -e "\n${YELLOW}${failed} serviço(s) não responderam. Verifique os logs em ${RUN_DIR}${NC}"
        return 1
    fi
    echo -e "\n${GREEN}Todos os serviços respondendo.${NC}"
    return 0
}

kill_by_pidfile() {
    local pid_file="$1"
    if ! pid_is_running "$pid_file"; then
        rm -f "$pid_file" || true
        return 0
    fi
    local pid
    pid="$(cat "$pid_file")"
    # Prefer killing process group to avoid leaving orphan children (e.g. uvicorn under a wrapper)
    kill -TERM -- "-$pid" >/dev/null 2>&1 || kill "$pid" >/dev/null 2>&1 || true
    sleep 0.8
    if kill -0 "$pid" >/dev/null 2>&1; then
        kill -KILL -- "-$pid" >/dev/null 2>&1 || kill -9 "$pid" >/dev/null 2>&1 || true
    fi
    rm -f "$pid_file" || true
}

kill_edge_hard() {
    # Para o edge de forma garantida: pid file + grep de processos + fuser
    kill_by_pidfile "$EDGE_PID_FILE"
    # Mata supervisor loop (sh -c) e uvicorn que ainda tenham a porta no nome
    local pids
    pids=$(ps aux | grep -E "uvicorn.*${EDGE_PORT}|sh -c.*${EDGE_PORT}" | grep -v grep | awk '{print $2}' || true)
    if [ -n "$pids" ]; then
        # shellcheck disable=SC2086
        kill -9 $pids 2>/dev/null || true
    fi
    sleep 1
    # Último recurso: fuser na porta
    if port_is_listening "$EDGE_PORT"; then
        fuser -k "${EDGE_PORT}/tcp" 2>/dev/null || true
        sleep 1
    fi
    rm -f "$EDGE_PID_FILE" || true
}

kokoro_is_up() {
    # Verifica se o Kokoro TTS está respondendo na porta configurada.
    local code
    code="$(curl -sS -o /dev/null -w "%{http_code}" --connect-timeout 2 --max-time 4 \
        "http://localhost:${KOKORO_PORT}/health" 2>/dev/null || echo "000")"
    [ "$code" = "200" ]
}

start_kokoro() {
    if kokoro_is_up; then
        echo -e "${YELLOW}AVISO:${NC} Kokoro TTS já está rodando na porta ${KOKORO_PORT}."
        return 0
    fi

    if [ -z "${KOKORO_DIR}" ] || [ ! -f "${KOKORO_DIR}/docker-compose.yml" ]; then
        echo -e "${YELLOW}AVISO:${NC} KOKORO_DIR não definido ou docker-compose.yml não encontrado em '${KOKORO_DIR}'."
        echo "  Defina KOKORO_DIR antes de rodar: export KOKORO_DIR=/caminho/para/kokoro"
        return 1
    fi

    if ! command -v docker &>/dev/null; then
        echo -e "${RED}ERRO:${NC} Docker não encontrado. Instale o Docker para subir o Kokoro."
        return 1
    fi

    echo -e "${BLUE}Iniciando Kokoro TTS via Docker Compose (${KOKORO_DIR})...${NC}"
    (cd "${KOKORO_DIR}" && docker compose up -d kokoro-api) || {
        echo -e "${RED}ERRO:${NC} Falha ao subir Kokoro. Veja: cd '${KOKORO_DIR}' && docker compose logs kokoro-api"
        return 1
    }

    echo -n "  Aguardando Kokoro responder (porta ${KOKORO_PORT})..."
    local elapsed=0
    while [ "$elapsed" -lt 60 ]; do
        if kokoro_is_up; then
            echo -e " ${GREEN}OK${NC}"
            echo -e "${GREEN}SUCESSO:${NC} Kokoro TTS iniciado em http://localhost:${KOKORO_PORT}"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
        echo -n "."
    done
    echo ""
    echo -e "${YELLOW}AVISO:${NC} Kokoro não respondeu em 60s. Pode estar ainda inicializando (modelos pesados)."
    echo "  Verifique: cd '${KOKORO_DIR}' && docker compose logs -f kokoro-api"
    return 1
}

stop_kokoro() {
    if [ -z "${KOKORO_DIR}" ] || [ ! -f "${KOKORO_DIR}/docker-compose.yml" ]; then
        echo -e "${YELLOW}AVISO:${NC} KOKORO_DIR não definido. Nada a parar."
        return 0
    fi
    echo -e "${BLUE}Parando Kokoro TTS...${NC}"
    (cd "${KOKORO_DIR}" && docker compose stop kokoro-api) && echo -e "${GREEN}OK.${NC}" || true
}

start_edge() {
    ensure_venv
    if pid_is_running "$EDGE_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} Edge já está em execução."
        return 0
    fi
    if port_is_listening "$EDGE_PORT"; then
        local pid
        pid="$(pid_from_port "$EDGE_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${EDGE_PORT} já está em uso; assumindo Edge já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$EDGE_PID_FILE"
        fi
        return 0
    fi

    echo -e "${BLUE}Iniciando Edge (API) em ${EDGE_URL}...${NC}"
    echo "Logs: $EDGE_LOG_FILE"

    (
        cd "$ROOT_DIR"
        source ./.venv/bin/activate
        export DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME EDGE_DEVICE_TOKEN EDGE_PORT EDGE_HOST PUBLIC_HOST
        # Run under a tiny supervisor loop so if uvicorn dies it comes back automatically.
        # Important: we keep PID file pointing to the wrapper, and stop() kills the process group.
        # sg lp = roda com grupo lp para poder escrever na impressora térmica (/dev/usb/lp1)
        nohup sg lp -c "
          set -e
          cd \"$ROOT_DIR\"
          export PATH=\"$ROOT_DIR/.venv/bin:\$PATH\"
          export DB_HOST=\"$DB_HOST\" DB_PORT=\"$DB_PORT\" DB_USER=\"$DB_USER\" DB_PASSWORD=\"$DB_PASSWORD\" DB_NAME=\"$DB_NAME\"
          export EDGE_DEVICE_TOKEN=\"$EDGE_DEVICE_TOKEN\" EDGE_PORT=\"$EDGE_PORT\" EDGE_HOST=\"$EDGE_HOST\" PUBLIC_HOST=\"$PUBLIC_HOST\"
          echo \"[edge-supervisor] starting at \$(date -Is)\"
          while true; do
            \"$ROOT_DIR/.venv/bin/python3\" -m uvicorn backend.edge.app:app --host \"$EDGE_HOST\" --port \"$EDGE_PORT\" \
              --timeout-keep-alive \"$EDGE_UVICORN_TIMEOUT_KEEP_ALIVE\" \
              --timeout-graceful-shutdown \"$EDGE_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN\" \
              $EDGE_UVICORN_EXTRA_ARGS
            code=\$?
            echo \"[edge-supervisor] uvicorn exited code=\$code at \$(date -Is); restarting in 1s\"
            sleep 1
          done
        " >"$EDGE_LOG_FILE" 2>&1 &
        echo $! > "$EDGE_PID_FILE"
    )

    if wait_for_edge 25; then
        echo -e "${GREEN}SUCESSO:${NC} Edge iniciado."
    else
        echo -e "${RED}ERRO:${NC} Edge não subiu (timeout). Veja logs: $EDGE_LOG_FILE"
        rm -f "$EDGE_PID_FILE" || true
        return 1
    fi
}

start_dashboard() {
    if pid_is_running "$DASHBOARD_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} Dashboard já está em execução."
        return 0
    fi
    if port_is_listening "$DASHBOARD_PORT"; then
        local pid
        pid="$(pid_from_port "$DASHBOARD_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${DASHBOARD_PORT} já está em uso; assumindo Dashboard já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$DASHBOARD_PID_FILE"
        fi
        return 0
    fi
    echo -e "${BLUE}Iniciando Dashboard (página principal) em ${DASHBOARD_URL}...${NC}"
    echo "Logs: $DASHBOARD_LOG_FILE"
    (
        cd "$ROOT_DIR"
        nohup ${PYTHON_HTTP} -m http.server "$DASHBOARD_PORT" --directory "${ROOT_DIR}/frontend/dashboard" >"$DASHBOARD_LOG_FILE" 2>&1 &
        echo $! > "$DASHBOARD_PID_FILE"
    )
    sleep 0.6
    if port_is_listening "$DASHBOARD_PORT"; then
        echo -e "${GREEN}SUCESSO:${NC} Dashboard iniciado."
    else
        echo -e "${RED}ERRO:${NC} Dashboard não subiu. Veja logs: $DASHBOARD_LOG_FILE"
        rm -f "$DASHBOARD_PID_FILE" || true
        return 1
    fi
}

start_tv() {
    if pid_is_running "$TV_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} TV já está em execução."
        return 0
    fi
    if port_is_listening "$TV_PORT"; then
        local pid
        pid="$(pid_from_port "$TV_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${TV_PORT} já está em uso; assumindo TV já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$TV_PID_FILE"
        fi
        return 0
    fi
    echo -e "${BLUE}Iniciando TV em ${TV_URL}...${NC}"
    echo "Logs: $TV_LOG_FILE"
    (
        cd "$ROOT_DIR"
        nohup ${PYTHON_HTTP} -m http.server "$TV_PORT" --directory "${ROOT_DIR}/frontend/tv" >"$TV_LOG_FILE" 2>&1 &
        echo $! > "$TV_PID_FILE"
    )
    sleep 0.6
    if port_is_listening "$TV_PORT"; then
        echo -e "${GREEN}SUCESSO:${NC} TV iniciada."
    else
        echo -e "${RED}ERRO:${NC} TV não subiu. Veja logs: $TV_LOG_FILE"
        rm -f "$TV_PID_FILE" || true
        return 1
    fi
}

start_test_ui() {
    if pid_is_running "$TEST_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} UI de teste já está em execução."
        return 0
    fi
    if port_is_listening "$TEST_PORT"; then
        local pid
        pid="$(pid_from_port "$TEST_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${TEST_PORT} já está em uso; assumindo Test UI já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$TEST_PID_FILE"
        fi
        return 0
    fi
    echo -e "${BLUE}Iniciando UI de teste em ${TEST_URL}...${NC}"
    echo "Logs: $TEST_LOG_FILE"
    (
        cd "$ROOT_DIR"
        nohup ${PYTHON_HTTP} -m http.server "$TEST_PORT" --directory "${ROOT_DIR}/frontend/operator-test" >"$TEST_LOG_FILE" 2>&1 &
        echo $! > "$TEST_PID_FILE"
    )
    sleep 0.6
    if port_is_listening "$TEST_PORT"; then
        echo -e "${GREEN}SUCESSO:${NC} UI de teste iniciada."
    else
        echo -e "${RED}ERRO:${NC} UI de teste não subiu. Veja logs: $TEST_LOG_FILE"
        rm -f "$TEST_PID_FILE" || true
        return 1
    fi
}

start_admin_ui() {
    if pid_is_running "$ADMIN_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} Admin Tenant já está em execução."
        return 0
    fi
    if port_is_listening "$ADMIN_PORT"; then
        local pid
        pid="$(pid_from_port "$ADMIN_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${ADMIN_PORT} já está em uso; assumindo Admin UI já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$ADMIN_PID_FILE"
        fi
        return 0
    fi
    echo -e "${BLUE}Iniciando Admin Tenant em ${ADMIN_URL}...${NC}"
    echo "Logs: $ADMIN_LOG_FILE"
    (
        cd "$ROOT_DIR"
        nohup ${PYTHON_HTTP} -m http.server "$ADMIN_PORT" --directory "${ROOT_DIR}/frontend/admin-tenant" >"$ADMIN_LOG_FILE" 2>&1 &
        echo $! > "$ADMIN_PID_FILE"
    )
    sleep 0.6
    if port_is_listening "$ADMIN_PORT"; then
        echo -e "${GREEN}SUCESSO:${NC} Admin Tenant iniciado."
    else
        echo -e "${RED}ERRO:${NC} Admin Tenant não subiu. Veja logs: $ADMIN_LOG_FILE"
        rm -f "$ADMIN_PID_FILE" || true
        return 1
    fi
}

start_operator_ui() {
    if pid_is_running "$OP_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} Operador já está em execução."
        return 0
    fi
    if port_is_listening "$OP_PORT"; then
        local pid
        pid="$(pid_from_port "$OP_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${OP_PORT} já está em uso; assumindo Operador já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$OP_PID_FILE"
        fi
        return 0
    fi
    echo -e "${BLUE}Iniciando Operador em ${OP_URL}...${NC}"
    echo "Logs: $OP_LOG_FILE"
    (
        cd "$ROOT_DIR"
        nohup ${PYTHON_HTTP} -m http.server "$OP_PORT" --directory "${ROOT_DIR}/frontend/operator" >"$OP_LOG_FILE" 2>&1 &
        echo $! > "$OP_PID_FILE"
    )
    sleep 0.6
    if port_is_listening "$OP_PORT"; then
        echo -e "${GREEN}SUCESSO:${NC} Operador iniciado."
    else
        echo -e "${RED}ERRO:${NC} Operador não subiu. Veja logs: $OP_LOG_FILE"
        rm -f "$OP_PID_FILE" || true
        return 1
    fi
}

start_totem_ui() {
    if pid_is_running "$TOTEM_PID_FILE"; then
        echo -e "${YELLOW}AVISO:${NC} Totem já está em execução."
        return 0
    fi
    if port_is_listening "$TOTEM_PORT"; then
        local pid
        pid="$(pid_from_port "$TOTEM_PORT")"
        echo -e "${YELLOW}AVISO:${NC} Porta ${TOTEM_PORT} já está em uso; assumindo Totem já rodando (pid=${pid:-?})."
        if [ -n "${pid}" ]; then
            echo "$pid" > "$TOTEM_PID_FILE"
        fi
        return 0
    fi
    echo -e "${BLUE}Iniciando Totem em ${TOTEM_URL}...${NC}"
    echo "Logs: $TOTEM_LOG_FILE"
    (
        cd "$ROOT_DIR"
        nohup ${PYTHON_HTTP} -m http.server "$TOTEM_PORT" --directory "${ROOT_DIR}/frontend/totem" >"$TOTEM_LOG_FILE" 2>&1 &
        echo $! > "$TOTEM_PID_FILE"
    )
    sleep 0.6
    if port_is_listening "$TOTEM_PORT"; then
        echo -e "${GREEN}SUCESSO:${NC} Totem iniciado."
    else
        echo -e "${RED}ERRO:${NC} Totem não subiu. Veja logs: $TOTEM_LOG_FILE"
        rm -f "$TOTEM_PID_FILE" || true
        return 1
    fi
}

stop_all() {
    echo -e "${BLUE}Parando serviços...${NC}"
    kill_by_pidfile "$TEST_PID_FILE"
    kill_by_pidfile "$TV_PID_FILE"
    kill_by_pidfile "$ADMIN_PID_FILE"
    kill_by_pidfile "$OP_PID_FILE"
    kill_by_pidfile "$TOTEM_PID_FILE"
    kill_by_pidfile "$DASHBOARD_PID_FILE"
    kill_edge_hard
    echo -e "${GREEN}OK.${NC}"
}

start_all() {
    # 1) Edge é obrigatório: sem API os outros não funcionam. Força reinício garantido.
    echo -e "${BLUE}Parando Edge (forçar reinício)...${NC}"
    kill_edge_hard
    if ! start_edge; then
        echo -e "${RED}Edge não iniciou. Abortando; os outros serviços não foram iniciados.${NC}"
        echo "Verifique: $EDGE_LOG_FILE"
        exit 1
    fi
    if ! wait_for_edge 10; then
        echo -e "${RED}Edge não respondeu na porta ${EDGE_PORT}. Abortando.${NC}"
        exit 1
    fi
    # 2) Com Edge no ar, inicia o resto em sequência.
    start_dashboard
    start_tv
    start_test_ui
    start_operator_ui
    start_admin_ui
    start_totem_ui

    echo -e "\n${GREEN}Processos iniciados.${NC}"
    echo "- Dashboard (página principal): ${DASHBOARD_URL}"
    echo "- Edge: ${EDGE_URL}"
    echo "- TV:   ${TV_URL}"
    echo "- Test: ${TEST_URL}"
    echo "- Operador: ${OP_URL}"
    echo "- Admin: ${ADMIN_URL}"
    echo "- Totem: ${TOTEM_URL}"

    # 3) Aguarda um pouco e testa se cada serviço responde via HTTP.
    sleep 3
    if ! verify_all_services; then
        echo -e "\n${YELLOW}Dica: se o Edge falhou, o venv pode ter path absoluto antigo. Recrie com:${NC}"
        echo "  rm -rf .venv && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt"
        exit 1
    fi
}

migrate_and_seed() {
    echo -e "${BLUE}Aplicando migrations + seed...${NC}"
    # reset=0 por padrão (não destrói dados)
    local reset="${1:-0}"
    curl -sS -X POST "${EDGE_URL}/admin/migrate?reset=${reset}" -H "Authorization: Bearer ${EDGE_DEVICE_TOKEN}" >/dev/null
    curl -sS -X POST "${EDGE_URL}/admin/seed" -H "Authorization: Bearer ${EDGE_DEVICE_TOKEN}" >/dev/null
    echo -e "${GREEN}OK.${NC}"
}

status_all() {
    echo -e "${BLUE}Status (Etapa 1)${NC}"
    if port_is_listening "$EDGE_PORT"; then
        echo -e "Edge (7071):  ${GREEN}ATIVO${NC}  ${EDGE_URL}"
    else
        if pid_is_running "$EDGE_PID_FILE"; then
            local pid
            pid="$(cat "$EDGE_PID_FILE" 2>/dev/null || true)"
            echo -e "Edge (7071):  ${YELLOW}TRAVADO${NC} (pid vivo sem LISTEN: ${pid:-?})  ${EDGE_URL}"
        else
            echo -e "Edge (7071):  ${RED}INATIVO${NC}  ${EDGE_URL}"
        fi
    fi
    echo -e "Dashboard(${DASHBOARD_PORT}): $(port_is_listening "$DASHBOARD_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${DASHBOARD_URL}"
    echo -e "TV   (${TV_PORT}):  $(port_is_listening "$TV_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${TV_URL}"
    echo -e "Teste(${TEST_PORT}): $(port_is_listening "$TEST_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${TEST_URL}"
    echo -e "Operador(${OP_PORT}): $(port_is_listening "$OP_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${OP_URL}"
    echo -e "Admin(${ADMIN_PORT}): $(port_is_listening "$ADMIN_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${ADMIN_URL}"
    echo -e "Totem(${TOTEM_PORT}): $(port_is_listening "$TOTEM_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${TOTEM_URL}"
    if kokoro_is_up; then
        echo -e "Kokoro(${KOKORO_PORT}): ${GREEN}ATIVO${NC}  http://localhost:${KOKORO_PORT}  [dir: ${KOKORO_DIR}]"
    else
        echo -e "Kokoro(${KOKORO_PORT}): ${YELLOW}INATIVO${NC}  (TTS desativado)  [dir: ${KOKORO_DIR}]"
    fi
    echo -e "Logs: ${RUN_DIR}"
}

tail_logs() {
    local which="${1:-edge}"
    case "$which" in
        edge) tail -n 200 -f "$EDGE_LOG_FILE" ;;
        dashboard) tail -n 200 -f "$DASHBOARD_LOG_FILE" ;;
        tv) tail -n 200 -f "$TV_LOG_FILE" ;;
        test) tail -n 200 -f "$TEST_LOG_FILE" ;;
        op) tail -n 200 -f "$OP_LOG_FILE" ;;
        admin) tail -n 200 -f "$ADMIN_LOG_FILE" ;;
        totem) tail -n 200 -f "$TOTEM_LOG_FILE" ;;
        *) echo -e "${RED}Uso:${NC} logs [edge|dashboard|tv|test|op|admin|totem]"; exit 1 ;;
    esac
}

# --- Menu Interativo (opcional) ---

show_menu() {
    echo -e "\n${BLUE}=====================================${NC}"
    echo -e "${BLUE}   Gerenciador — ${PROJECT_NAME}             ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo "1. Start (Dashboard + Edge + TV + Test + Operador + Admin + Totem)"
    echo "2. Stop (todos)"
    echo "3. Status"
    echo "4. Migrate+Seed (reset=0)"
    echo "5. Migrate+Seed (reset=1)"
    echo "6. Logs Edge"
    echo "7. Logs Dashboard"
    echo "8. Logs TV"
    echo "9. Logs Test UI"
    echo "10. Logs Operador"
    echo "11. Logs Admin Tenant"
    echo "12. Logs Totem"
    echo "13. Kokoro TTS — Iniciar"
    echo "14. Kokoro TTS — Parar"
    echo "15. Sair"
    echo -e "${BLUE}------------------------------------${NC}"
}

# --- Loop Principal ---

main() {
    if [ ! -f "${ROOT_DIR}/backend/edge/app.py" ]; then
        echo -e "${RED}ERRO:${NC} Execute este script a partir do diretório raiz do repositório (onde está backend/edge/app.py)."
        exit 1
    fi

    # Modo não-interativo
    if [ "${1:-}" != "" ]; then
        case "${1}" in
            start) start_all ;;
            stop) stop_all ;;
            restart) stop_all; start_all ;;
            status) status_all ;;
            migrate) migrate_and_seed "${2:-0}" ;;
            logs) tail_logs "${2:-edge}" ;;
            kokoro)
                case "${2:-status}" in
                    start)  start_kokoro ;;
                    stop)   stop_kokoro ;;
                    status) kokoro_is_up \
                        && echo -e "Kokoro TTS: ${GREEN}ATIVO${NC}  http://localhost:${KOKORO_PORT}" \
                        || echo -e "Kokoro TTS: ${YELLOW}INATIVO${NC}" ;;
                    *)
                        echo "Uso: ./gerenciar.sh kokoro [start|stop|status]"
                        exit 1
                        ;;
                esac
                ;;
            *)
                echo "Uso: ./gerenciar.sh [start|stop|restart|status|migrate [0|1]|logs [edge|dashboard|tv|test|op|admin|totem]|kokoro [start|stop|status]]"
                exit 1
                ;;
        esac
        exit 0
    fi

    while true; do
        show_menu
        read -p "Escolha uma opção [1-15]: " choice

        case $choice in
            1)
                start_all
                ;;
            2)
                stop_all
                ;;
            3)
                status_all
                ;;
            4)
                migrate_and_seed 0
                ;;
            5)
                migrate_and_seed 1
                ;;
            6)
                tail_logs edge
                ;;
            7)
                tail_logs dashboard
                ;;
            8)
                tail_logs tv
                ;;
            9)
                tail_logs test
                ;;
            10)
                tail_logs op
                ;;
            11)
                tail_logs admin
                ;;
            12)
                tail_logs totem
                ;;
            13)
                start_kokoro
                ;;
            14)
                stop_kokoro
                ;;
            15)
                echo -e "${BLUE}Saindo...${NC}"
                exit 0
                ;;
            *)
                echo -e "${RED}Opção inválida. Tente novamente.${NC}"
                ;;
        esac
        echo ""
        read -n 1 -s -r -p "Pressione qualquer tecla para continuar..."
        clear
    done
}

# Inicia o script
main "$@"
