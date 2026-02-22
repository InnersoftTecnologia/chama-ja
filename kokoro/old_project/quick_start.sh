#!/bin/bash

# ============================================================================
# Kokoro TTS - Quick Start Script
# 
# Inicia todos os serviços e demonstra a funcionalidade
# 
# Uso: bash quickstart.sh
# ============================================================================

set -e

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# ============================================================================
# Funções
# ============================================================================

print_header() {
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║ $1"
    echo -e "${BLUE}╚════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# ============================================================================
# Verificações Prévias
# ============================================================================

print_header "VERIFICAÇÕES PRÉ-REQUISITOS"

# Verificar Docker
if ! command -v docker &> /dev/null; then
    print_error "Docker não encontrado"
    echo "Instale em: https://www.docker.com/products/docker-desktop"
    exit 1
fi
print_success "Docker instalado"

# Verificar Docker Compose
if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose não encontrado"
    exit 1
fi
print_success "Docker Compose instalado"

# Verificar Python (para demo Python)
if ! command -v python3 &> /dev/null; then
    print_warning "Python3 não encontrado (pule demo Python)"
else
    print_success "Python3 instalado"
fi

# Verificar Node.js (para demo Node)
if ! command -v node &> /dev/null; then
    print_warning "Node.js não encontrado (pule demo Node)"
else
    print_success "Node.js instalado ($(node -v))"
fi

# Verificar PHP
if ! command -v php &> /dev/null; then
    print_warning "PHP não encontrado (pule demo PHP)"
else
    print_success "PHP instalado ($(php -v | head -n 1))"
fi

# ============================================================================
# Iniciar Serviços
# ============================================================================

print_header "INICIANDO SERVIÇOS DOCKER"

# Verificar se há containers antigos
if docker ps -a --format '{{.Names}}' | grep -q "kokoro"; then
    print_warning "Containers Kokoro já existem"
    read -p "Deseja removê-los? (s/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        docker compose down --volumes
        print_success "Containers removidos"
    fi
fi

# Iniciar docker compose
print_info "Iniciando Docker Compose..."
docker compose up -d

print_success "Serviços Docker iniciados"

# Aguardar Kokoro estar pronto
print_info "Aguardando Kokoro estar pronto..."
for i in {1..30}; do
    if curl -s http://localhost:8880/health > /dev/null; then
        print_success "Kokoro respondendo"
        break
    fi
    echo -n "."
    sleep 1
done

# ============================================================================
# Testar Conexão
# ============================================================================

print_header "TESTANDO CONEXÃO"

# Testar Kokoro
if curl -s http://localhost:8880/health | grep -q "ok"; then
    print_success "Kokoro API: CONECTADO"
else
    print_error "Kokoro API: NÃO RESPONDENDO"
    exit 1
fi

# Testar Node.js (se compose tem o serviço)
if curl -s http://localhost:7000/health > /dev/null; then
    print_success "Node.js API: CONECTADO"
else
    print_warning "Node.js API: NÃO RESPONDENDO (verifique logs)"
fi

# ============================================================================
# Demostração Python
# ============================================================================

if command -v python3 &> /dev/null; then
    print_header "DEMO: PYTHON"
    
    # Criar ambiente virtual se não existir
    if [ ! -d "venv" ]; then
        print_info "Criando ambiente virtual Python..."
        python3 -m venv venv
        # Ativar e instalar
        source venv/bin/activate
        pip install -q requests python-dotenv
    else
        source venv/bin/activate
    fi
    
    print_info "Executando demonstração Python..."
    python3 kokoro_demo.py 2>&1 | head -50
    print_success "Demo Python concluída (cheque audio_output/ para arquivos)"
    deactivate
fi

# ============================================================================
# Demonstração PHP
# ============================================================================

if command -v php &> /dev/null; then
    print_header "DEMO: PHP"
    
    print_info "Testando síntese com PHP..."
    
    php -r "
    require 'kokoro_tts.php';
    \$tts = new KokoroTTS('http://localhost:8880');
    
    try {
        \$audio = \$tts->synthesize('Olá! Esta é uma demonstração em PHP com síntese de voz em português brasileiro.');
        if (\$audio) {
            \$tts->saveToFile(\$audio, 'demo_php.mp3');
            echo \"✅ Áudio gerado: demo_php.mp3\\n\";
        }
    } catch (Exception \$e) {
        echo \"❌ Erro: \" . \$e->getMessage() . \"\\n\";
    }
    " 2>&1
fi

# ============================================================================
# Demonstração Node.js
# ============================================================================

if command -v node &> /dev/null; then
    print_header "DEMO: NODE.JS"
    
    # Verificar se package.json existe
    if [ -f "package.json" ]; then
        if [ ! -d "node_modules" ]; then
            print_info "Instalando dependências Node.js..."
            npm install -q
        fi
        
        print_info "Testando síntese com Node.js..."
        
        node -e "
        const axios = require('axios');
        
        axios.post('http://localhost:7000/synthesize', {
            text: 'Olá! Esta é uma demonstração em Node.js com síntese de voz em português brasileiro.',
            voice: 'pf_dora',
            speed: 1.0
        })
        .then(res => {
            console.log('✅ Áudio gerado');
            console.log('   Tamanho: ' + res.data.size + ' bytes');
            console.log('   Voz: ' + res.data.voice);
        })
        .catch(err => {
            console.error('❌ Erro:', err.message);
        });
        " 2>&1
    else
        print_warning "package.json não encontrado"
    fi
fi

# ============================================================================
# Resumo
# ============================================================================

print_header "✅ SETUP COMPLETO"

echo -e "${GREEN}Serviços ativos:${NC}"
echo ""
echo -e "  🎤 Kokoro TTS API:"
echo -e "     ${BLUE}http://localhost:8880${NC}"
echo -e "     Documentação: ${BLUE}http://localhost:8880/docs${NC}"
echo ""
echo -e "  🐍 Demo Python:"
echo -e "     ${BLUE}python3 kokoro_demo.py${NC}"
echo ""
echo -e "  🟢 Node.js API:"
echo -e "     ${BLUE}http://localhost:7000${NC}"
echo -e "     Endpoints: /status, /synthesize, /batch, /voices, etc."
echo ""
echo -e "  🐘 PHP:"
echo -e "     ${BLUE}Classe: kokoro_tts.php${NC}"
echo -e "     Exemplo: ${BLUE}php -r 'require \"kokoro_tts.php\"; ...'${NC}"
echo ""
echo -e "  📁 Áudio gerado:"
echo -e "     ${BLUE}./audio_output/${NC}"
echo ""

echo -e "${YELLOW}Próximas etapas:${NC}"
echo "  1. Teste os endpoints da API Node.js"
echo "  2. Integre com seu n8n workflow"
echo "  3. Use as classes PHP/Python no seu código"
echo "  4. Veja os arquivos de áudio em audio_output/"
echo ""

echo -e "${BLUE}Comandos úteis:${NC}"
echo "  docker compose ps               # Ver status dos containers"
echo "  docker compose logs -f          # Ver logs em tempo real"
echo "  docker compose down             # Parar todos os serviços"
echo ""

print_success "Sistema Kokoro TTS pronto para usar! 🚀"
