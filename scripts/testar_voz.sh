#!/bin/bash
# scripts/testar_voz.sh — Teste de síntese de voz (TTS) via Kokoro

uso() {
  cat <<EOF

Uso: ./scripts/testar_voz.sh -t "Texto a pronunciar" [opções]

Opções:
  -t "texto"        Texto a ser pronunciado
  -voz VALOR        Voz a usar (padrão: feminina)
  --limpar-cache    Remove todos os MP3 do cache (.run/tts_cache/)
  -h, --help        Exibe esta ajuda

Vozes disponíveis:
  feminina          Dora   — voz feminina natural  (padrão)
  masculina         Alex   — voz masculina natural
  santa             Santa  — voz masculina alternativa

Exemplos:
  ./scripts/testar_voz.sh -t "Atenção, senha B zero um sete, guichê doze"
  ./scripts/testar_voz.sh -voz masculina -t "Senha A zero zero um. Guichê três."
  ./scripts/testar_voz.sh -voz santa -t "Dirija-se ao guichê preferencial."
  ./scripts/testar_voz.sh --limpar-cache

EOF
}

VOICE_ID="pf_dora"
VOICE_LABEL="Dora (feminina)"
TEXTO=""
CACHE_DIR="$(cd "$(dirname "$0")/.." && pwd)/.run/tts_cache"
TMP_FILE="/tmp/chamada_tts_teste.mp3"

# Parse de argumentos
while [[ $# -gt 0 ]]; do
  case "$1" in
    -voz)
      case "$2" in
        feminina|dora)
          VOICE_ID="pf_dora"
          VOICE_LABEL="Dora (feminina)"
          ;;
        masculina|alex)
          VOICE_ID="pm_alex"
          VOICE_LABEL="Alex (masculino)"
          ;;
        santa)
          VOICE_ID="pm_santa"
          VOICE_LABEL="Santa (masculino)"
          ;;
        *)
          echo "Voz inválida: '$2'. Use: feminina, masculina ou santa."
          exit 1
          ;;
      esac
      shift 2
      ;;
    -t)
      TEXTO="$2"
      shift 2
      ;;
    --limpar-cache|-c)
      if [ -d "$CACHE_DIR" ]; then
        COUNT=$(ls "$CACHE_DIR"/*.mp3 2>/dev/null | wc -l)
        rm -f "$CACHE_DIR"/*.mp3
        echo "Cache limpo: $COUNT arquivo(s) removido(s) em $CACHE_DIR"
      else
        echo "Cache vazio (diretório não existe)."
      fi
      exit 0
      ;;
    -h|--help)
      uso
      exit 0
      ;;
    *)
      echo "Opção desconhecida: '$1'"
      uso
      exit 1
      ;;
  esac
done

if [ -z "$TEXTO" ]; then
  echo "Erro: informe o texto com -t \"...\""
  uso
  exit 1
fi

echo ""
echo "  Voz   : $VOICE_LABEL"
echo "  Texto : \"$TEXTO\""
echo ""

PAYLOAD=$(python3 -c "
import json, sys
print(json.dumps({
  'model': 'kokoro',
  'input': sys.argv[1],
  'voice': sys.argv[2],
  'response_format': 'mp3',
  'speed': 1.0
}))
" "$TEXTO" "$VOICE_ID")

HTTP=$(curl -s -X POST http://localhost:8880/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -o "$TMP_FILE" \
  -w "%{http_code}")

if [ "$HTTP" != "200" ]; then
  echo "Erro ao chamar Kokoro: HTTP $HTTP"
  exit 1
fi

SIZE=$(wc -c < "$TMP_FILE")
echo "MP3 gerado: ${SIZE} bytes — reproduzindo..."
mpv --no-video --really-quiet "$TMP_FILE"
echo ""
