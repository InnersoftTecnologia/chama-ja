#!/usr/bin/env bash
# =============================================================================
# Chama Já — Print Agent (Linux / macOS)
# Versão: 1.0
#
# Uso:
#   chmod +x print-agent.sh
#   ./print-agent.sh
#
# Requisitos: python3 (presente em quase todo Linux/macOS moderno).
# Sem instalação de pacotes extras.
# =============================================================================

# ---- CONFIGURAÇÃO -----------------------------------------------------------
export AGENT_SERVER="https://innersoft.com.br/chama-ja/fcosta-gus/api"
export AGENT_TOKEN="COLE-O-TOKEN-AQUI"
POLL_SEC=2
# -----------------------------------------------------------------------------

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] [$1] $2"; }

log "INFO" "Print Agent iniciado. Servidor: $AGENT_SERVER"
log "INFO" "Pressione Ctrl+C para encerrar."
echo ""

# Loop principal: a cada ciclo chama o mini-agente Python embutido
while true; do
    python3 - <<'PYEOF'
import base64, json, os, socket, sys, urllib.request, urllib.error
from datetime import datetime

server = os.environ["AGENT_SERVER"]
token  = os.environ["AGENT_TOKEN"]
ts     = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def http_get(url):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())

def http_post(url, body_dict):
    data = json.dumps(body_dict).encode()
    req  = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass

def send_escpos(ip, port, raw_bytes):
    with socket.create_connection((ip, port), timeout=5) as s:
        s.sendall(raw_bytes)

try:
    resp = http_get(f"{server}/print-agent/jobs")
except Exception as e:
    print(f"[{ts()}] [ERRO] Falha ao consultar servidor: {e}", flush=True)
    sys.exit(0)

jobs = resp.get("jobs", [])
if jobs:
    print(f"[{ts()}] [INFO] {len(jobs)} job(s) pendente(s).", flush=True)

for job in jobs:
    job_id  = job["id"]
    code    = job["ticket_code"]
    pr_ip   = job.get("printer_ip") or ""
    pr_port = int(job.get("printer_port") or 9100)
    b64data = job.get("print_data_b64") or ""

    if not pr_ip:
        print(f"[{ts()}] [AVISO] Job {code}: IP da impressora não configurado.", flush=True)
        http_post(f"{server}/print-agent/jobs/{job_id}/ack",
                  {"status": "failed", "error": "printer_ip not configured"})
        continue

    if not b64data:
        print(f"[{ts()}] [AVISO] Job {code}: dados ESC/POS ausentes.", flush=True)
        http_post(f"{server}/print-agent/jobs/{job_id}/ack",
                  {"status": "failed", "error": "print_data_b64 empty"})
        continue

    print(f"[{ts()}] [INFO] Imprimindo {code} → {pr_ip}:{pr_port} ...", flush=True)
    try:
        send_escpos(pr_ip, pr_port, base64.b64decode(b64data))
        print(f"[{ts()}] [OK]   Job {code} ({job_id}): impresso.", flush=True)
        http_post(f"{server}/print-agent/jobs/{job_id}/ack", {"status": "printed"})
    except Exception as e:
        print(f"[{ts()}] [ERRO] Job {code} ({job_id}): {e}", flush=True)
        http_post(f"{server}/print-agent/jobs/{job_id}/ack",
                  {"status": "failed", "error": str(e)})
PYEOF

    sleep "$POLL_SEC"
done
