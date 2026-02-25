#!/usr/bin/env bash
# Prepara o logo para impressão térmica: 1-bit, largura máx 576px, sem anti-aliasing.
# Uso: ./scripts/preparar_logo_ticket.sh [entrada.png] [saida.png]
# No Linux pode usar ImageMagick ou Python (Pillow). Este script usa o que estiver disponível.

set -e
ENTRADA="${1:-$(dirname "$0")/../images/logo_tenant.png}"
SAIDA="${2:-$(dirname "$0")/../images/logo_tenant_1bit.png}"
LARGURA="${TICKET_LOGO_WIDTH:-576}"

if [ ! -f "$ENTRADA" ]; then
  echo "Arquivo não encontrado: $ENTRADA"
  exit 1
fi

if command -v convert >/dev/null 2>&1; then
  # ImageMagick: resize, threshold 50%, 1-bit
  convert "$ENTRADA" -resize "${LARGURA}x" -threshold 50% -monochrome -colors 2 "$SAIDA"
  echo "Logo preparado com ImageMagick: $SAIDA"
elif command -v python3 >/dev/null 2>&1; then
  python3 -c "
from PIL import Image
import sys
wmax = int('$LARGURA')
img = Image.open('$ENTRADA').convert('L')
img.thumbnail((wmax, wmax * 2), Image.LANCZOS)
w, h = img.size
w = ((w + 7) // 8) * 8
if img.size[0] != w:
    img = img.resize((w, h), Image.LANCZOS)
img = img.point(lambda x: 0 if x < 128 else 255, mode='1')
img.save('$SAIDA')
print('Logo preparado com Pillow:', '$SAIDA')
"
else
  echo "Instale ImageMagick (convert) ou Python+Pillow para usar este script."
  echo "  sudo apt install imagemagick"
  echo "  ou: pip install Pillow"
  exit 1
fi
