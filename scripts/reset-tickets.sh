#!/bin/bash
# reset-tickets.sh — Limpa todas as senhas e reseta a numeração para zero.
# Use em manutenções antes de uma nova operação do dia.
#
# Apaga: tickets, calls (histórico TV), ticket_print_jobs
# Reseta: ticket_sequences (numeração volta para A-001 / P-001)
# Preserva: tenants, usuários, operadores, guichês, serviços, configurações de TV

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Carrega as mesmas variáveis do gerenciar.sh
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_USER="${DB_USER:-mysql}"
DB_PASSWORD="${DB_PASSWORD:-mysql}"
DB_NAME="${DB_NAME:-chamador}"

MYSQL_CMD="mysql -h${DB_HOST} -P${DB_PORT} -u${DB_USER} -p${DB_PASSWORD} ${DB_NAME}"

# ── Cores ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}${CYAN}║        Chama Já — Reset de Senhas            ║${RESET}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════╝${RESET}"
echo ""

# ── Situação atual ────────────────────────────────────────────────────────────
echo -e "${BOLD}Situação atual:${RESET}"
$MYSQL_CMD --table -e "
  SELECT
    (SELECT COUNT(*) FROM tickets)                             AS total_tickets,
    (SELECT COUNT(*) FROM tickets WHERE status='waiting')     AS aguardando,
    (SELECT COUNT(*) FROM tickets WHERE status='called')      AS chamados,
    (SELECT COUNT(*) FROM tickets WHERE status='in_service')  AS em_atendimento,
    (SELECT COUNT(*) FROM tickets WHERE status='completed')   AS concluidos,
    (SELECT COUNT(*) FROM calls)                              AS historico_tv,
    (SELECT COUNT(*) FROM ticket_print_jobs)                  AS print_jobs,
    (SELECT COALESCE(MAX(current_number),0) FROM ticket_sequences) AS ultima_numeracao
  \G" 2>/dev/null | grep -v "^\*\*\*" | sed 's/^ */  /'
echo ""

# ── Confirmação ───────────────────────────────────────────────────────────────
echo -e "${YELLOW}${BOLD}ATENÇÃO: Esta operação é IRREVERSÍVEL.${RESET}"
echo -e "Serão apagados: tickets, histórico da TV (calls), print jobs."
echo -e "A numeração de senhas voltará a ${BOLD}A-001 / P-001${RESET}."
echo -e "Operadores, guichês, serviços e configurações ${GREEN}NÃO serão afetados${RESET}."
echo ""

# Aceita --yes para uso em automações (sem prompt interativo)
if [[ "${1:-}" == "--yes" ]]; then
    echo -e "${YELLOW}Modo não-interativo (--yes). Prosseguindo...${RESET}"
else
    read -rp "$(echo -e "${BOLD}Digite RESET para confirmar: ${RESET}")" CONFIRM
    if [[ "$CONFIRM" != "RESET" ]]; then
        echo -e "${RED}Cancelado.${RESET}"
        exit 0
    fi
fi

echo ""
echo -e "${CYAN}Executando reset...${RESET}"

$MYSQL_CMD -e "
SET FOREIGN_KEY_CHECKS=0;
DELETE FROM calls;
DELETE FROM ticket_print_jobs;
DELETE FROM tickets;
UPDATE ticket_sequences SET current_number = 0;
SET FOREIGN_KEY_CHECKS=1;
" 2>/dev/null

# ── Limpa arquivos de impressão em disco (.run/prints/) ──────────────────────
PRINTS_DIR="${ROOT_DIR}/.run/prints"
if [[ -d "$PRINTS_DIR" ]]; then
    COUNT_FILES=$(find "$PRINTS_DIR" -maxdepth 1 -name "*.txt" | wc -l)
    if [[ "$COUNT_FILES" -gt 0 ]]; then
        rm -f "${PRINTS_DIR}"/*.txt
        echo -e "  ${GREEN}✓${RESET} ${COUNT_FILES} arquivo(s) de impressão removidos de .run/prints/"
    fi
fi

# ── Resultado ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Reset concluído com sucesso.${RESET}"
$MYSQL_CMD --table -e "
  SELECT
    (SELECT COUNT(*) FROM tickets)        AS tickets,
    (SELECT COUNT(*) FROM calls)          AS historico_tv,
    (SELECT COUNT(*) FROM ticket_print_jobs) AS print_jobs,
    (SELECT COALESCE(SUM(current_number),0) FROM ticket_sequences) AS numeracao
" 2>/dev/null
echo ""
echo -e "A próxima senha emitida começará do ${BOLD}001${RESET}."
echo ""
