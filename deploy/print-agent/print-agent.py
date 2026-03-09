#!/usr/bin/env python3
"""
Chama Já — Print Agent (Linux / macOS / qualquer sistema com Python 3.6+)
Versão: 1.0

Uso:
    python3 print-agent.py

Requisitos: Python 3.6+ — nenhum pacote externo (stdlib pura).
"""

import base64
import json
import socket
import time
import urllib.error
import urllib.request
from datetime import datetime

# ---- CONFIGURAÇÃO -----------------------------------------------------------
SERVER = "https://innersoft.com.br/chama-ja/fcosta-gus/api"
TOKEN  = "6c79f979-1bad-11f1-aa97-fa27c9035795"
POLL_S = 2          # Intervalo de polling em segundos
# -----------------------------------------------------------------------------


def log(level: str, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] [{level}] {msg}", flush=True)


def http_get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def http_post(url: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url, data=data,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception:
        return {}


def send_escpos(ip: str, port: int, raw_bytes: bytes) -> None:
    with socket.create_connection((ip, port), timeout=5) as s:
        s.sendall(raw_bytes)


def process_jobs() -> None:
    try:
        resp = http_get(f"{SERVER}/print-agent/jobs")
    except Exception as e:
        log("ERRO", f"Falha ao consultar servidor: {e}")
        return

    jobs = resp.get("jobs", [])
    if jobs:
        log("INFO", f"{len(jobs)} job(s) pendente(s).")

    for job in jobs:
        job_id  = job["id"]
        code    = job["ticket_code"]
        pr_ip   = (job.get("printer_ip") or "").strip()
        pr_port = int(job.get("printer_port") or 9100)
        b64data = (job.get("print_data_b64") or "").strip()

        if not pr_ip:
            log("AVISO", f"Job {code} ({job_id}): IP da impressora não configurado.")
            http_post(f"{SERVER}/print-agent/jobs/{job_id}/ack",
                      {"status": "failed", "error": "printer_ip not configured"})
            continue

        if not b64data:
            log("AVISO", f"Job {code} ({job_id}): dados ESC/POS ausentes.")
            http_post(f"{SERVER}/print-agent/jobs/{job_id}/ack",
                      {"status": "failed", "error": "print_data_b64 empty"})
            continue

        log("INFO", f"Imprimindo {code} → {pr_ip}:{pr_port} ...")
        try:
            send_escpos(pr_ip, pr_port, base64.b64decode(b64data))
            log("OK  ", f"Job {code} ({job_id}): impresso com sucesso.")
            http_post(f"{SERVER}/print-agent/jobs/{job_id}/ack", {"status": "printed"})
        except Exception as e:
            log("ERRO", f"Job {code} ({job_id}): {e}")
            http_post(f"{SERVER}/print-agent/jobs/{job_id}/ack",
                      {"status": "failed", "error": str(e)})


def main() -> None:
    log("INFO", f"Print Agent iniciado. Servidor: {SERVER}")
    log("INFO", "Pressione Ctrl+C para encerrar.")
    print()
    while True:
        process_jobs()
        time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        log("INFO", "Encerrado pelo usuário.")
