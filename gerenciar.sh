#!/bin/bash

set -euo pipefail

# --- Configurações (Etapa 1) ---
PROJECT_NAME="chamador"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_DIR="${ROOT_DIR}/.run"
mkdir -p "$RUN_DIR"

# Portas (escopo 7070–7079)
EDGE_HOST="${EDGE_HOST:-0.0.0.0}"
EDGE_PORT="${EDGE_PORT:-7071}"
TV_PORT="${TV_PORT:-7073}"          # 7070 costuma estar ocupada no host; 7073 é fallback
TEST_PORT="${TEST_PORT:-7072}"
ADMIN_PORT="${ADMIN_PORT:-7075}"
OP_PORT="${OP_PORT:-7074}"
TOTEM_PORT="${TOTEM_PORT:-7076}"

EDGE_URL="http://localhost:${EDGE_PORT}"
TV_URL="http://localhost:${TV_PORT}"
TEST_URL="http://localhost:${TEST_PORT}"
ADMIN_URL="http://localhost:${ADMIN_PORT}"
OP_URL="http://localhost:${OP_PORT}"
TOTEM_URL="http://localhost:${TOTEM_PORT}"

# DB (MariaDB local)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-mysql}"
DB_PASSWORD="${DB_PASSWORD:-mysql}"
DB_NAME="${DB_NAME:-chamador}"

# Token simples (MVP)
EDGE_DEVICE_TOKEN="${EDGE_DEVICE_TOKEN:-dev-edge-token}"

# PIDs/logs
EDGE_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_edge.pid"
TV_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_tv.pid"
TEST_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_test.pid"
ADMIN_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_admin.pid"
OP_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_op.pid"
TOTEM_PID_FILE="${RUN_DIR}/${PROJECT_NAME}_totem.pid"

EDGE_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_edge.log"
TV_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_tv.log"
TEST_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_test.log"
ADMIN_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_admin.log"
OP_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_op.log"
TOTEM_LOG_FILE="${RUN_DIR}/${PROJECT_NAME}_totem.log"

# Uvicorn tuning (helps avoid "stuck shutting down" with SSE/keep-alive)
EDGE_UVICORN_TIMEOUT_KEEP_ALIVE="${EDGE_UVICORN_TIMEOUT_KEEP_ALIVE:-15}"
EDGE_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN="${EDGE_UVICORN_TIMEOUT_GRACEFUL_SHUTDOWN:-5}"
EDGE_UVICORN_EXTRA_ARGS="${EDGE_UVICORN_EXTRA_ARGS:-}"

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

# Aguarda a porta do Edge ficar em LISTEN (até max_sec segundos). Retorna 0 se ok, 1 se timeout.
wait_for_edge() {
    local max_sec="${1:-30}"
    local elapsed=0
    while [ "$elapsed" -lt "$max_sec" ]; do
        if port_is_listening "$EDGE_PORT"; then
            return 0
        fi
        sleep 1
        elapsed=$((elapsed + 1))
    done
    return 1
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
        export DB_HOST DB_PORT DB_USER DB_PASSWORD DB_NAME EDGE_DEVICE_TOKEN EDGE_PORT EDGE_HOST
        # Run under a tiny supervisor loop so if uvicorn dies it comes back automatically.
        # Important: we keep PID file pointing to the wrapper, and stop() kills the process group.
        nohup bash -lc "
          set -e
          cd \"$ROOT_DIR\"
          source ./.venv/bin/activate
          export DB_HOST=\"$DB_HOST\" DB_PORT=\"$DB_PORT\" DB_USER=\"$DB_USER\" DB_PASSWORD=\"$DB_PASSWORD\" DB_NAME=\"$DB_NAME\"
          export EDGE_DEVICE_TOKEN=\"$EDGE_DEVICE_TOKEN\" EDGE_PORT=\"$EDGE_PORT\" EDGE_HOST=\"$EDGE_HOST\"
          echo \"[edge-supervisor] starting at \$(date -Is)\" 
          while true; do
            uvicorn backend.edge.app:app --host \"$EDGE_HOST\" --port \"$EDGE_PORT\" \
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
        nohup python3 -m http.server "$TV_PORT" --directory "${ROOT_DIR}/frontend/tv" >"$TV_LOG_FILE" 2>&1 &
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
        nohup python3 -m http.server "$TEST_PORT" --directory "${ROOT_DIR}/frontend/operator-test" >"$TEST_LOG_FILE" 2>&1 &
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
        nohup python3 -m http.server "$ADMIN_PORT" --directory "${ROOT_DIR}/frontend/admin-tenant" >"$ADMIN_LOG_FILE" 2>&1 &
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
        nohup python3 -m http.server "$OP_PORT" --directory "${ROOT_DIR}/frontend/operator" >"$OP_LOG_FILE" 2>&1 &
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
        nohup python3 -m http.server "$TOTEM_PORT" --directory "${ROOT_DIR}/frontend/totem" >"$TOTEM_LOG_FILE" 2>&1 &
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
    kill_by_pidfile "$EDGE_PID_FILE"
    echo -e "${GREEN}OK.${NC}"
}

start_all() {
    # 1) Edge é obrigatório: sem API os outros não funcionam. Força reinício do Edge para evitar estado travado.
    echo -e "${BLUE}Parando Edge (forçar reinício)...${NC}"
    kill_by_pidfile "$EDGE_PID_FILE"
    sleep 1
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
    start_tv
    start_test_ui
    start_operator_ui
    start_admin_ui
    start_totem_ui
    echo -e "\n${GREEN}Tudo pronto.${NC}"
    echo "- Edge: ${EDGE_URL}"
    echo "- TV:   ${TV_URL}"
    echo "- Test: ${TEST_URL}"
    echo "- Operador: ${OP_URL}"
    echo "- Admin: ${ADMIN_URL}"
    echo "- Totem: ${TOTEM_URL}"
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
    echo -e "TV   (${TV_PORT}):  $(port_is_listening "$TV_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${TV_URL}"
    echo -e "Teste(${TEST_PORT}): $(port_is_listening "$TEST_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${TEST_URL}"
    echo -e "Operador(${OP_PORT}): $(port_is_listening "$OP_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${OP_URL}"
    echo -e "Admin(${ADMIN_PORT}): $(port_is_listening "$ADMIN_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${ADMIN_URL}"
    echo -e "Totem(${TOTEM_PORT}): $(port_is_listening "$TOTEM_PORT" && echo -e "${GREEN}ATIVO${NC}" || echo -e "${RED}INATIVO${NC}")  ${TOTEM_URL}"
    echo -e "Logs: ${RUN_DIR}"
}

tail_logs() {
    local which="${1:-edge}"
    case "$which" in
        edge) tail -n 200 -f "$EDGE_LOG_FILE" ;;
        tv) tail -n 200 -f "$TV_LOG_FILE" ;;
        test) tail -n 200 -f "$TEST_LOG_FILE" ;;
        op) tail -n 200 -f "$OP_LOG_FILE" ;;
        admin) tail -n 200 -f "$ADMIN_LOG_FILE" ;;
        totem) tail -n 200 -f "$TOTEM_LOG_FILE" ;;
        *) echo -e "${RED}Uso:${NC} logs [edge|tv|test|op|admin|totem]"; exit 1 ;;
    esac
}

# --- Menu Interativo (opcional) ---

show_menu() {
    echo -e "\n${BLUE}=====================================${NC}"
    echo -e "${BLUE}   Gerenciador Etapa 1 — Chamador    ${NC}"
    echo -e "${BLUE}=====================================${NC}"
    echo "1. Start (Edge + TV + Test UI + Operador + Admin + Totem)"
    echo "2. Stop (todos)"
    echo "3. Status"
    echo "4. Migrate+Seed (reset=0)"
    echo "5. Migrate+Seed (reset=1)"
    echo "6. Logs Edge"
    echo "7. Logs TV"
    echo "8. Logs Test UI"
    echo "9. Logs Operador"
    echo "10. Logs Admin Tenant"
    echo "11. Logs Totem"
    echo "12. Sair"
    echo -e "${BLUE}------------------------------------${NC}"
}

# --- Loop Principal ---

main() {
    if [ ! -f "${ROOT_DIR}/backend/edge/app.py" ]; then
        echo -e "${RED}ERRO:${NC} Este script deve ser executado a partir do diretório raiz do projeto 'chamador'."
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
            *)
                echo "Uso: ./gerenciar.sh [start|stop|restart|status|migrate [0|1]|logs [edge|tv|test|op|admin|totem]]"
                exit 1
                ;;
        esac
        exit 0
    fi

    while true; do
        show_menu
        read -p "Escolha uma opção [1-12]: " choice

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
                tail_logs tv
                ;;
            8)
                tail_logs test
                ;;
            9)
                tail_logs op
                ;;
            10)
                tail_logs admin
                ;;
            11)
                tail_logs totem
                ;;
            12)
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
