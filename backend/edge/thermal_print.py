"""
Impressão térmica ESC/POS para tickets do totem (impressora 80-IX / POS80).
Gera recibo com senha em destaque, código de barras CODE128 e QR Code.
Suporta logo em raster no topo (PNG/JPG).
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional, Union

logger = logging.getLogger(__name__)

# Largura máxima em pixels (80-IX: 576 dots/line)
PRINTER_DOTS_PER_LINE = 576

# Codificação para texto no recibo (impressora 80-IX: WPC1252 / OEM860)
TICKET_ENCODING = "cp1252"


def _esc_init() -> bytes:
    return b"\x1b\x40"


def _esc_center() -> bytes:
    return b"\x1b\x61\x01"


def _esc_left() -> bytes:
    return b"\x1b\x61\x00"


def _esc_expanded(on: bool = True) -> bytes:
    return b"\x1b\x21\x30" if on else b"\x1b\x21\x00"


def _esc_bold(on: bool = True) -> bytes:
    return b"\x1b\x45\x01" if on else b"\x1b\x45\x00"


def _gs_barcode_code128(data: bytes) -> bytes:
    if len(data) > 255:
        data = data[:255]
    return b"\x1d\x6b\x49" + bytes([len(data)]) + data


def _gs_qrcode(data: str) -> bytes:
    data_bytes = data.encode("utf-8")
    L = len(data_bytes)
    model = b"\x1d\x28\x6b\x04\x00\x31\x41\x00\x01\x01\x31"
    pL = (L + 2) & 0xFF
    pH = ((L + 2) >> 8) & 0xFF
    store = b"\x1d\x28\x6b" + bytes([pL, pH]) + b"\x32\x41\x00" + data_bytes + b"\x00"
    print_cmd = b"\x1d\x28\x6b\x04\x00\x31\x51\x30\x00"
    return model + store + print_cmd


def _text(s: str) -> bytes:
    """Encode text for thermal receipt (CP1252 for Portuguese)."""
    return (s or "").encode(TICKET_ENCODING, errors="replace")


def _image_to_escpos_raster(
    image_path: str,
    max_width_pixels: int = PRINTER_DOTS_PER_LINE,
) -> Optional[bytes]:
    """
    Converte uma imagem (PNG/JPG) para comando raster ESC/POS GS v 0.
    Retorna bytes do comando ou None em caso de erro.
    Largura em bytes = pixels/8; altura em dots; dados em colunas (8 dots/byte, MSB=topo).
    """
    try:
        from PIL import Image

        img = Image.open(image_path)
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P" and "transparency" in img.info:
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                bg.paste(img, mask=img.split()[-1])
            else:
                bg.paste(img)
            img.close()
            img = bg
        elif img.mode != "L" and img.mode != "RGB":
            img = img.convert("RGB")

        if img.mode == "RGB":
            img = img.convert("L")

        w, h = img.size
        if w > max_width_pixels:
            ratio = max_width_pixels / w
            new_w = max_width_pixels
            new_h = max(1, int(h * ratio))
            img = img.resize((new_w, new_h), Image.LANCZOS)
            w, h = new_w, new_h

        # Garantir largura múltipla de 8
        w = ((w + 7) // 8) * 8
        if img.size[0] != w:
            img = img.resize((w, h), Image.LANCZOS)

        # 1-bit: imprimir (1) onde for escuro, fundo (0) onde for claro
        # Logo "texto branco no fundo vermelho" -> em L o texto fica 255, fundo ~80 -> inverter: imprimir onde L >= 128
        img = img.point(lambda x: 255 if x < 128 else 0, mode="1")  # 0 = imprimir (preto), 255 = não imprimir
        px = img.load()
        width_bytes = w // 8
        height_dots = h

        # ESC *: column-major — n bytes por banda (cada byte = 8 dots verticais numa coluna), MSB = topo
        out = bytearray()
        for band in range((height_dots + 7) // 8):
            out.extend(bytes([0x1B, 0x2A, 0x00, width_bytes]))
            for col in range(width_bytes):
                byte_val = 0
                for i in range(8):
                    row = band * 8 + i
                    if row < height_dots:
                        for bit in range(8):
                            x = col * 8 + bit
                            if x < w and px[x, row] == 0:  # 0 = imprimir (preto)
                                byte_val |= 1 << (7 - i)
                                break
                out.append(byte_val)
            out.append(0x0A)  # LF

        img.close()
        return bytes(out)
    except Exception as e:
        logger.warning("Falha ao converter logo para ESC/POS: %s", e)
        return None


def build_ticket_escpos(
    ticket_code: str,
    service_name: str,
    priority: str,
    issued_at_str: str,
    tenant_name: Optional[str] = None,
    base_url: Optional[str] = None,
    ticket_id: Optional[str] = None,
    logo_path: Optional[str] = None,
    include_barcode: bool = False,
    include_qr: bool = False,
) -> bytes:
    """
    Monta a sequência ESC/POS para um recibo de senha (formato modelo: sem código de barras).
    Layout: logo (opcional), tenant, SERVIÇO, PRIORIDADE, SENHA em destaque, EMITIDO EM + hora.
    """
    buf = _esc_init() + _esc_center()
    if logo_path and os.path.isfile(logo_path):
        logo_bytes = _image_to_escpos_raster(logo_path)
        if logo_bytes:
            buf += logo_bytes + b"\n"
    if tenant_name:
        name_parts = tenant_name.split(" - ", 1) if " - " in tenant_name else [tenant_name]
        buf += _esc_expanded(True)
        for part in name_parts:
            buf += _text(f"{part}\n")
        buf += _esc_expanded(False)
        buf += _text("--------------------------------\n")
    buf += b"\n"

    # SERVIÇO: rótulo normal + valor expandido
    buf += _text("SERVICO:\n")
    buf += _esc_expanded(True)
    buf += _text(f"{service_name}\n")
    buf += _esc_expanded(False)
    buf += b"\n"

    # PRIORIDADE: rótulo normal + valor expandido
    buf += _text("PRIORIDADE:\n")
    buf += _esc_expanded(True)
    buf += _text(f"{priority}\n")
    buf += _esc_expanded(False)
    buf += b"\n"

    # SENHA: [código em destaque expandido]
    buf += _text("SENHA: ")
    buf += _esc_expanded(True)
    buf += _text(f"{ticket_code}\n")
    buf += _esc_expanded(False)
    buf += b"\n"

    # EMITIDO EM: data e hora em linhas separadas (texto menor)
    parts = issued_at_str.split(" ", 1)
    date_part = parts[0] if parts else issued_at_str
    time_part = parts[1] if len(parts) > 1 else ""
    buf += _esc_bold(True)
    buf += _text(f"EMITIDO EM: {date_part}\n")
    if time_part:
        buf += _text(f"{time_part}\n")
    buf += _esc_bold(False)

    # Avançar papel para a guilhotina cortar num local seguro
    buf += b"\n\n\n\n\n\n\n\n"
    buf += b"\x1d\x56\x00"  # GS V 0 - Corte
    return buf


def send_to_printer(escpos_bytes: bytes, device: Optional[str] = None) -> bool:
    """
    Envia os bytes ESC/POS para o dispositivo da impressora.
    Retorna True se enviou com sucesso, False caso contrário (sem falhar).
    """
    path = (device or os.environ.get("PRINTER_DEVICE") or "/dev/usb/lp1").strip()
    if not path:
        return False
    if not os.path.exists(path):
        logger.debug("Impressora nao encontrada: %s", path)
        return False
    try:
        with open(path, "wb") as f:
            f.write(escpos_bytes)
        logger.info("Ticket enviado para impressora: %s", path)
        return True
    except PermissionError:
        logger.warning("Sem permissao para escrever na impressora %s (execute com grupo lp ou root)", path)
        return False
    except OSError as e:
        logger.warning("Erro ao enviar para impressora %s: %s", path, e)
        return False


def print_ticket(
    ticket_data: Dict[str, Any],
    base_url: Optional[str] = None,
    device: Optional[str] = None,
) -> bool:
    """
    Gera o recibo ESC/POS do ticket e envia para a impressora térmica.
    ticket_data deve conter: ticket_code, service_name, priority e issued_at (datetime).
    Retorna True se imprimiu, False caso contrário.
    """
    from datetime import datetime

    ticket_code = ticket_data.get("ticket_code") or ""
    service_name = ticket_data.get("service_name") or ""
    priority = ticket_data.get("priority") or "normal"
    issued = ticket_data.get("issued_at")
    if isinstance(issued, datetime):
        from datetime import timezone, timedelta
        BRT = timezone(timedelta(hours=-3))
        if issued.tzinfo is not None:
            issued = issued.astimezone(BRT)
        issued_str = issued.strftime("%d/%m/%Y %H:%M:%S")
    else:
        issued_str = str(issued or "")

    tenant_name = ticket_data.get("tenant_name")

    base = base_url or os.environ.get("TOTEM_BASE_URL", "").rstrip("/")
    ticket_id_str = (ticket_data.get("ticket_id") or "").strip()
    logo_path = ticket_data.get("logo_path") or os.environ.get("TICKET_LOGO_PATH", "").strip() or None

    escpos = build_ticket_escpos(
        ticket_code=ticket_code,
        service_name=service_name,
        priority="Preferencial" if priority == "preferential" else "Normal",
        issued_at_str=issued_str,
        tenant_name=tenant_name,
        base_url=base if base else None,
        ticket_id=ticket_id_str if ticket_id_str else None,
        logo_path=logo_path,
        include_barcode=False,
        include_qr=False,
    )
    return send_to_printer(escpos, device=device)
