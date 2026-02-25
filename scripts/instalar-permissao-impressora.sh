#!/usr/bin/env bash
# Instala permissão permanente para a impressora térmica POS80/80-IX.
# Assim qualquer usuário (e o backend) pode escrever em /dev/usb/lp1 sem sudo nem grupo lp.
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RULES_SRC="${ROOT}/scripts/udev-printer-pos80.rules"
if [ ! -f "$RULES_SRC" ]; then
  echo "Arquivo não encontrado: $RULES_SRC"
  exit 1
fi
echo "Instalando regra udev para impressora POS80..."
sudo cp "$RULES_SRC" /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=usbmisc
echo "Pronto. Reconecte o cabo da impressora USB ou reinicie o micro."
echo "Depois disso, /dev/usb/lp1 ficará com permissão 0666 (todos podem imprimir)."
