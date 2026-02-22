# =============================================================================
# KOKORO TTS - TESTE NO WINDOWS (SEM CONTAINERS)
# =============================================================================
# Script PowerShell para testar Kokoro TTS diretamente
# Data: 27/01/2025
# Autor: Bruno (Assistente IA)

Write-Host "🎤 KOKORO TTS - TESTE NO WINDOWS" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan

# Verificar se Python está instalado
Write-Host "`n1. Verificando Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✅ Python encontrado: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Python não encontrado!" -ForegroundColor Red
    Write-Host "   Instale Python 3.8+ de: https://python.org" -ForegroundColor Yellow
    exit 1
}

# Verificar se Node.js está instalado
Write-Host "`n2. Verificando Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version 2>&1
    Write-Host "✅ Node.js encontrado: $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ Node.js não encontrado!" -ForegroundColor Red
    Write-Host "   Instale Node.js 14+ de: https://nodejs.org" -ForegroundColor Yellow
    exit 1
}

# Verificar se PHP está instalado
Write-Host "`n3. Verificando PHP..." -ForegroundColor Yellow
try {
    $phpVersion = php --version 2>&1 | Select-Object -First 1
    Write-Host "✅ PHP encontrado: $phpVersion" -ForegroundColor Green
} catch {
    Write-Host "❌ PHP não encontrado!" -ForegroundColor Red
    Write-Host "   Instale PHP 8.0+ de: https://php.net" -ForegroundColor Yellow
    exit 1
}

# Criar ambiente virtual Python
Write-Host "`n4. Configurando ambiente Python..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "✅ Ambiente virtual já existe" -ForegroundColor Green
} else {
    python -m venv venv
    Write-Host "✅ Ambiente virtual criado" -ForegroundColor Green
}

# Ativar ambiente virtual e instalar dependências
Write-Host "`n5. Instalando dependências Python..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"
pip install requests python-dotenv
Write-Host "✅ Dependências Python instaladas" -ForegroundColor Green

# Instalar dependências Node.js
Write-Host "`n6. Instalando dependências Node.js..." -ForegroundColor Yellow
if (Test-Path "node_modules") {
    Write-Host "✅ node_modules já existe" -ForegroundColor Green
} else {
    npm install
    Write-Host "✅ Dependências Node.js instaladas" -ForegroundColor Green
}

# Criar diretório de áudio
Write-Host "`n7. Criando diretórios..." -ForegroundColor Yellow
if (-not (Test-Path "audio_output")) {
    New-Item -ItemType Directory -Name "audio_output" | Out-Null
    Write-Host "✅ Diretório audio_output criado" -ForegroundColor Green
} else {
    Write-Host "✅ Diretório audio_output já existe" -ForegroundColor Green
}

Write-Host "`n🎯 AMBIENTE CONFIGURADO COM SUCESSO!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green

Write-Host "`n📋 PRÓXIMOS PASSOS:" -ForegroundColor Cyan
Write-Host "1. Inicie o servidor Kokoro (você precisa fazer isso manualmente)" -ForegroundColor White
Write-Host "2. Teste Python: python kokoro_demo.py" -ForegroundColor White
Write-Host "3. Teste Node.js: npm start" -ForegroundColor White
Write-Host "4. Teste PHP: php kokoro_tts.php" -ForegroundColor White

Write-Host "`n⚠️  IMPORTANTE:" -ForegroundColor Yellow
Write-Host "Você precisa iniciar o servidor Kokoro primeiro!" -ForegroundColor White
Write-Host "Opções:" -ForegroundColor White
Write-Host "- Docker: docker run -d -p 8880:8880 --name kokoro ghcr.io/remsky/kokoro-fastapi-cpu:latest" -ForegroundColor Gray
Write-Host "- Ou usar um servidor Kokoro externo" -ForegroundColor Gray

Write-Host "`n🚀 Para testar agora:" -ForegroundColor Cyan
Write-Host "python kokoro_demo.py" -ForegroundColor White
