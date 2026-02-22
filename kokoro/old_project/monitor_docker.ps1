# =============================================================================
# KOKORO TTS - MONITOR DOCKER
# =============================================================================
# Script para monitorar o download e inicialização do Kokoro
# Data: 27/01/2025

Write-Host "🐳 MONITORANDO DOCKER KOKORO" -ForegroundColor Cyan
Write-Host "=============================" -ForegroundColor Cyan

Write-Host "`n📥 Status do Download:" -ForegroundColor Yellow

# Verificar se a imagem está sendo baixada
$images = docker images 2>$null | Select-String "kokoro"
if ($images) {
    Write-Host "✅ Imagem Kokoro encontrada:" -ForegroundColor Green
    $images | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
} else {
    Write-Host "⏳ Imagem ainda sendo baixada..." -ForegroundColor Yellow
}

# Verificar containers
Write-Host "`n🐳 Status dos Containers:" -ForegroundColor Yellow
$containers = docker ps -a 2>$null | Select-String "kokoro"
if ($containers) {
    Write-Host "✅ Container Kokoro encontrado:" -ForegroundColor Green
    $containers | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
} else {
    Write-Host "⏳ Container ainda não criado..." -ForegroundColor Yellow
}

# Verificar se a porta está em uso
Write-Host "`n🌐 Status da Porta 8880:" -ForegroundColor Yellow
$portCheck = netstat -an | Select-String ":8880"
if ($portCheck) {
    Write-Host "✅ Porta 8880 em uso:" -ForegroundColor Green
    $portCheck | ForEach-Object { Write-Host "   $_" -ForegroundColor Gray }
} else {
    Write-Host "⏳ Porta 8880 ainda não está em uso..." -ForegroundColor Yellow
}

Write-Host "`n📋 PRÓXIMOS PASSOS:" -ForegroundColor Cyan
Write-Host "1. Aguarde o download terminar" -ForegroundColor White
Write-Host "2. Execute: docker ps" -ForegroundColor White
Write-Host "3. Teste: python kokoro_demo.py" -ForegroundColor White

Write-Host "`n⏰ Para monitorar continuamente:" -ForegroundColor Cyan
Write-Host "while (`$true) { docker ps; Start-Sleep 10 }" -ForegroundColor Gray


