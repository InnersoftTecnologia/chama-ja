#!/usr/bin/env python3
"""
Mock Thermal Printer — simula a impressora ESC/POS para testes locais.
Escuta em TCP :9100, recebe os bytes, salva em arquivo e exibe resumo.

Uso: python3 mock-printer.py
"""
import os
import socket
from datetime import datetime

HOST = "0.0.0.0"
PORT = 9100
SAVE_DIR = "mock-prints"

os.makedirs(SAVE_DIR, exist_ok=True)

def summarize(data: bytes) -> str:
    """Extrai texto legível dos bytes ESC/POS (ignora bytes de controle)."""
    text = ""
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x1b or b == 0x1d:   # ESC / GS — pula o comando
            i += 2
            continue
        if 0x20 <= b <= 0x7e or b in (0x0a, 0x0d):
            text += chr(b)
        i += 1
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n  ".join(lines[:20])

def ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print(f"[{ts()}] Mock Printer escutando em {HOST}:{PORT}")
print(f"[{ts()}] Arquivos salvos em ./{SAVE_DIR}/")
print(f"[{ts()}] Pressione Ctrl+C para encerrar.\n")

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(5)
    while True:
        conn, addr = srv.accept()
        with conn:
            data = b""
            conn.settimeout(2.0)
            try:
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except socket.timeout:
                pass

            fname = os.path.join(SAVE_DIR, f"print-{datetime.now().strftime('%H%M%S')}.bin")
            with open(fname, "wb") as f:
                f.write(data)

            print(f"[{ts()}] Recebido de {addr[0]} — {len(data)} bytes → {fname}")
            print(f"  Conteúdo legível:\n  {summarize(data)}")
            print()
