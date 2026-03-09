# =============================================================================
# Chama Já — Print Agent (Windows PowerShell)
# Versão: 1.0
#
# Uso: .\print-agent.ps1
# Requisitos: Windows 7+ com PowerShell 3+. Nenhuma instalação adicional.
#
# Configure as variáveis abaixo e execute no PowerShell:
#   powershell -ExecutionPolicy Bypass -File .\print-agent.ps1
# =============================================================================

# ---- CONFIGURAÇÃO -----------------------------------------------------------
$SERVER    = "https://innersoft.com.br/chama-ja/fcosta-gus/api"   # URL da API
$TOKEN     = "COLE-O-TOKEN-AQUI"                                   # Token do Admin Tenant
$POLL_MS   = 2000                                                  # Intervalo de polling (ms)
# -----------------------------------------------------------------------------

$ErrorActionPreference = "Continue"

function Write-Log {
    param([string]$msg, [string]$level = "INFO")
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$ts] [$level] $msg"
}

function Send-ToThermalPrinter {
    param(
        [string]$ip,
        [int]$port,
        [byte[]]$data
    )
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $client.ReceiveTimeout = 5000
        $client.SendTimeout    = 5000
        $client.Connect($ip, $port)
        $stream = $client.GetStream()
        $stream.Write($data, 0, $data.Length)
        $stream.Flush()
        return $true
    } catch {
        Write-Log "Erro TCP ${ip}:${port} — $_" "ERRO"
        return $false
    } finally {
        if ($client -ne $null) { $client.Close() }
    }
}

Write-Log "Print Agent iniciado. Servidor: $SERVER"
Write-Log "Pressione Ctrl+C para encerrar."
Write-Host ""

$headers = @{ "Authorization" = "Bearer $TOKEN" }

while ($true) {
    try {
        $resp = Invoke-RestMethod `
            -Uri     "$SERVER/print-agent/jobs" `
            -Method  GET `
            -Headers $headers `
            -ErrorAction Stop

        $jobs = $resp.jobs
        if ($jobs.Count -gt 0) {
            Write-Log "$($jobs.Count) job(s) pendente(s)."
        }

        foreach ($job in $jobs) {
            $jobId   = $job.id
            $code    = $job.ticket_code
            $prIp    = $job.printer_ip
            $prPort  = [int]($job.printer_port)
            $b64data = $job.print_data_b64

            if ([string]::IsNullOrEmpty($prIp)) {
                Write-Log "Job $code ($jobId): IP da impressora não configurado — ignorando." "AVISO"
                $ackBody = '{"status":"failed","error":"printer_ip not configured"}'
                Invoke-RestMethod `
                    -Uri         "$SERVER/print-agent/jobs/$jobId/ack" `
                    -Method      POST `
                    -Headers     $headers `
                    -ContentType "application/json" `
                    -Body        $ackBody | Out-Null
                continue
            }

            if ([string]::IsNullOrEmpty($b64data)) {
                Write-Log "Job $code ($jobId): dados ESC/POS ausentes — ignorando." "AVISO"
                $ackBody = '{"status":"failed","error":"print_data_b64 empty"}'
                Invoke-RestMethod `
                    -Uri         "$SERVER/print-agent/jobs/$jobId/ack" `
                    -Method      POST `
                    -Headers     $headers `
                    -ContentType "application/json" `
                    -Body        $ackBody | Out-Null
                continue
            }

            # Decodifica base64 → bytes ESC/POS
            $escposBytes = [Convert]::FromBase64String($b64data)

            Write-Log "Imprimindo $code → ${prIp}:${prPort} ..."
            $ok = Send-ToThermalPrinter -ip $prIp -port $prPort -data $escposBytes

            if ($ok) {
                $ackBody = '{"status":"printed"}'
                Write-Log "Job $code ($jobId): impresso com sucesso." "OK"
            } else {
                $ackBody = "{`"status`":`"failed`",`"error`":`"TCP send failed to ${prIp}:${prPort}`"}"
                Write-Log "Job $code ($jobId): falha na impressão." "ERRO"
            }

            try {
                Invoke-RestMethod `
                    -Uri         "$SERVER/print-agent/jobs/$jobId/ack" `
                    -Method      POST `
                    -Headers     $headers `
                    -ContentType "application/json" `
                    -Body        $ackBody | Out-Null
            } catch {
                Write-Log "Falha ao confirmar job $jobId: $_" "ERRO"
            }
        }

    } catch {
        Write-Log "Erro na consulta ao servidor: $_" "ERRO"
    }

    Start-Sleep -Milliseconds $POLL_MS
}
