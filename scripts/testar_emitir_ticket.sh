#!/usr/bin/env bash
# Testa emissão de ticket pela API (para ver formato e imprimir no térmico).
# Uso: ./scripts/testar_emitir_ticket.sh [BASE_URL]
# Ex.: ./scripts/testar_emitir_ticket.sh
#      ./scripts/testar_emitir_ticket.sh http://localhost:7071

set -e
BASE="${1:-http://localhost:7071}"
BASE="${BASE%/}"
TOKEN="${EDGE_DEVICE_TOKEN:-dev-edge-token}"

echo "=== Listando serviços ($BASE) ==="
SERVICES=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE/totem/services")
echo "$SERVICES" | python3 -m json.tool 2>/dev/null || echo "$SERVICES"

SERVICE_ID=$(echo "$SERVICES" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    arr = data if isinstance(data, list) else data.get('services', data)
    if arr and len(arr) > 0:
        print(arr[0]['id'])
    else:
        print('', end='')
except Exception:
    print('', end='')
" 2>/dev/null)

if [ -z "$SERVICE_ID" ]; then
    echo "Nenhum serviço ativo encontrado. Crie um tenant e um serviço no painel admin."
    exit 1
fi

echo ""
echo "=== Emitindo ticket (service_id=$SERVICE_ID) ==="
RESP=$(curl -s -X POST "$BASE/totem/emit" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\": \"$SERVICE_ID\"}")
echo "$RESP" | python3 -m json.tool 2>/dev/null || echo "$RESP"
echo ""
echo "Se a impressora estiver conectada e PRINTER_ENABLED=1, o recibo já foi impresso."
