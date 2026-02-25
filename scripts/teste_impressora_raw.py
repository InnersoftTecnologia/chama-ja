#!/usr/bin/env python3
"""
Teste RAW ESC/POS para impressora térmica 80-IX (USB).
Inclui: texto expandido, código de barras CODE128 e QR Code.
Uso: sudo python3 teste_impressora_raw.py
"""
import os
import sys

DEV = "/dev/usb/lp1"


def esc_pos_init():
    return b"\x1b\x40"  # ESC @


def esc_pos_center():
    return b"\x1b\x61\x01"  # ESC a 1


def esc_pos_left():
    return b"\x1b\x61\x00"  # ESC a 0


def esc_pos_expanded(on=True):
    # ESC ! n: 0x08=altura dupla, 0x10=largura dupla, 0x18=ambos
    return b"\x1b\x21\x30" if on else b"\x1b\x21\x00"


def esc_pos_barcode_code128(data: bytes):
    # GS k m n d1...dn | m=73 (CODE128), n=len(data)
    if len(data) > 255:
        data = data[:255]
    n = len(data)
    return b"\x1d\x6b\x49" + bytes([n]) + data  # GS k 73 n data


def esc_pos_qrcode(data: str):
    # QR Code ESC/POS: modelo 2, armazenar dados, imprimir
    data_bytes = data.encode("utf-8")
    L = len(data_bytes)

    # 1) Selecionar modelo QR (Model 2), módulo 4, correção de erro L
    # GS ( k pL pH cn fn [parâmetros]
    model = b"\x1d\x28\x6b\x04\x00\x31\x41\x00\x01\x01\x31"

    # 2) Armazenar dados: cn=50 fn=65, m=00, dados, 00
    pL = (L + 2) & 0xFF
    pH = ((L + 2) >> 8) & 0xFF
    store = b"\x1d\x28\x6b" + bytes([pL, pH]) + b"\x32\x41\x00" + data_bytes + b"\x00"

    # 3) Imprimir símbolo: cn=49 fn=81, parâmetros 00 00 (2 bytes) -> pL=4
    print_cmd = b"\x1d\x28\x6b\x04\x00\x31\x51\x30\x00"

    return model + store + print_cmd


def main():
    if not os.path.exists(DEV):
        print(f"Dispositivo não encontrado: {DEV}")
        sys.exit(1)

    buf = (
        esc_pos_init()
        + esc_pos_center()
        + b"  *** TESTE RAW ***\n"
        + b"  Chama Ja!\n"
        + esc_pos_left()
        + b"Data: 24/02/2025\n"
    )

    # --- TEXTO EXPANDIDO (dupla altura + dupla largura) ---
    buf += b"\n"
    buf += esc_pos_expanded(True)
    buf += b"TEXTO EXPANDIDO\n"
    buf += b"Chama Ja!\n"
    buf += esc_pos_expanded(False)
    buf += b"\n"

    # --- CÓDIGO DE BARRAS CODE128 ---
    buf += b"Codigo de barras CODE128:\n"
    buf += esc_pos_barcode_code128(b"CHAMAJA")
    buf += b"\n\n"

    # --- QR CODE ---
    buf += b"QR Code:\n"
    buf += esc_pos_qrcode("https://chama-ja.example.com/senha/123")
    buf += b"\n\n\n"
    buf += b"\x1d\x56\x00"  # GS V 0 - Corte

    try:
        with open(DEV, "wb") as f:
            f.write(buf)
        print("Comando enviado. Verifique a impressora.")
    except PermissionError:
        print("Sem permissão. Execute: sudo python3", __file__)
        sys.exit(1)
    except Exception as e:
        print("Erro:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
