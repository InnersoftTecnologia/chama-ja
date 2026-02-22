#!/bin/bash

# ==============================================================================
# Kokoro TTS - Script de Síntese de Voz
# ==============================================================================
# Uso: tts.sh "Texto a ser convertido" [arquivo_destino.mp3] [voz]
#
# Vozes disponíveis:
#   pf_dora  - Feminina (padrão)
#   pm_alex  - Masculino
#   pm_santa - Masculino
# ==============================================================================

# Configurações
KOKORO_API="http://localhost:7000/synthesize"
DEFAULT_VOICE="pf_dora"
DEFAULT_OUTPUT="/tmp/kokoro_output.mp3"
AUTO_PLAY=true  # Tocar automaticamente após gerar

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Função de ajuda
show_help() {
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  Kokoro TTS - Script de Síntese de Voz${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Uso:"
    echo "  tts.sh \"Texto a ser convertido\" [arquivo_destino.mp3] [voz]"
    echo ""
    echo "Parâmetros:"
    echo "  texto              Texto para converter em áudio (obrigatório)"
    echo "  arquivo_destino    Caminho do arquivo MP3 de saída (opcional)"
    echo "                     Padrão: $DEFAULT_OUTPUT"
    echo "  voz                Voz a utilizar (opcional)"
    echo "                     Padrão: $DEFAULT_VOICE"
    echo ""
    echo "Vozes disponíveis:"
    echo "  pf_dora   - Feminina, Português BR (padrão)"
    echo "  pm_alex   - Masculino, Português BR"
    echo "  pm_santa  - Masculino, Português BR"
    echo ""
    echo "Exemplos:"
    echo "  tts.sh \"Olá, mundo!\""
    echo "  tts.sh \"Bom dia\" saudacao.mp3"
    echo "  tts.sh \"Teste de voz\" teste.mp3 pm_alex"
    echo "  tts.sh \"Olá\" - pm_santa  # Toca direto (não salva)"
    echo ""
    echo "Opções:"
    echo "  -h, --help         Mostra esta ajuda"
    echo "  -l, --list         Lista vozes disponíveis"
    echo "  -n, --no-play      Não toca o áudio (apenas salva)"
    echo ""
    echo "Nota: Por padrão, o áudio é tocado automaticamente após ser gerado."
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Função para listar vozes
list_voices() {
    echo -e "${BLUE}Consultando vozes disponíveis...${NC}"
    curl -s "$KOKORO_API" 2>/dev/null | grep -q "synthesis" || {
        curl -s "http://localhost:7000/voices" | jq '.' 2>/dev/null || {
            echo -e "${RED}Erro: Não foi possível conectar ao servidor Kokoro${NC}"
            echo -e "${YELLOW}Certifique-se de que o servidor está rodando em http://localhost:7000${NC}"
            exit 1
        }
    }
}

# Verificar dependências
check_dependencies() {
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}Erro: curl não está instalado${NC}"
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        echo -e "${YELLOW}Aviso: jq não está instalado (funcionalidade limitada)${NC}"
    fi
}

# Processar argumentos
PLAY_AFTER=$AUTO_PLAY  # Usar configuração padrão
TEXT=""
OUTPUT=""
VOICE=""

while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -l|--list)
            list_voices
            exit 0
            ;;
        -n|--no-play)
            PLAY_AFTER=false
            shift
            ;;
        *)
            if [ -z "$TEXT" ]; then
                TEXT="$1"
            elif [ -z "$OUTPUT" ]; then
                OUTPUT="$1"
            elif [ -z "$VOICE" ]; then
                VOICE="$1"
            else
                echo -e "${RED}Erro: Muitos argumentos${NC}"
                show_help
                exit 1
            fi
            shift
            ;;
    esac
done

# Validar texto
if [ -z "$TEXT" ]; then
    echo -e "${RED}Erro: Texto não fornecido${NC}"
    show_help
    exit 1
fi

# Definir valores padrão
if [ -z "$OUTPUT" ]; then
    OUTPUT="$DEFAULT_OUTPUT"
fi

if [ -z "$VOICE" ]; then
    VOICE="$DEFAULT_VOICE"
fi

# Se output for "-", tocar direto sem salvar
PLAY_ONLY=false
if [ "$OUTPUT" = "-" ]; then
    PLAY_ONLY=true
    OUTPUT="/tmp/kokoro_temp_$$.mp3"
    PLAY_AFTER=true
fi

# Verificar dependências
check_dependencies

# Gerar áudio
echo -e "${BLUE}Gerando áudio...${NC}"
echo -e "  Texto: ${GREEN}$TEXT${NC}"
echo -e "  Voz: ${GREEN}$VOICE${NC}"
echo -e "  Arquivo: ${GREEN}$OUTPUT${NC}"

# Fazer requisição à API
RESPONSE=$(curl -s -X POST "$KOKORO_API" \
    -H "Content-Type: application/json" \
    -d "{\"text\":\"$TEXT\",\"voice\":\"$VOICE\"}")

# Verificar se houve erro
if echo "$RESPONSE" | grep -q '"success":false' 2>/dev/null || [ -z "$RESPONSE" ]; then
    echo -e "${RED}Erro ao gerar áudio${NC}"
    if command -v jq &> /dev/null; then
        echo "$RESPONSE" | jq '.' 2>/dev/null || echo "$RESPONSE"
    else
        echo "$RESPONSE"
    fi
    exit 1
fi

# Extrair e decodificar áudio
if command -v jq &> /dev/null; then
    echo "$RESPONSE" | jq -r '.audio' | base64 -d > "$OUTPUT"
else
    # Fallback sem jq (mais frágil)
    echo "$RESPONSE" | grep -o '"audio":"[^"]*"' | sed 's/"audio":"//;s/"$//' | base64 -d > "$OUTPUT"
fi

# Verificar se o arquivo foi criado
if [ ! -f "$OUTPUT" ] || [ ! -s "$OUTPUT" ]; then
    echo -e "${RED}Erro: Falha ao criar arquivo de áudio${NC}"
    exit 1
fi

# Mostrar informações do arquivo
FILE_SIZE=$(du -h "$OUTPUT" | cut -f1)
echo -e "${GREEN}✓ Áudio gerado com sucesso!${NC}"
echo -e "  Tamanho: ${GREEN}$FILE_SIZE${NC}"

# Tocar áudio se solicitado
if [ "$PLAY_AFTER" = true ]; then
    if command -v mpv &> /dev/null; then
        echo -e "${BLUE}Tocando áudio...${NC}"
        mpv --no-video --really-quiet "$OUTPUT"
    elif command -v ffplay &> /dev/null; then
        echo -e "${BLUE}Tocando áudio...${NC}"
        ffplay -nodisp -autoexit -loglevel quiet "$OUTPUT"
    else
        echo -e "${YELLOW}Aviso: Nenhum player de áudio encontrado (mpv ou ffplay)${NC}"
    fi
fi

# Limpar arquivo temporário se foi modo "play only"
if [ "$PLAY_ONLY" = true ]; then
    rm -f "$OUTPUT"
else
    echo -e "${BLUE}Arquivo salvo em: ${GREEN}$OUTPUT${NC}"
fi
