# start-all.ps1 — Inicializador Unificado do Ecossistema Second Brain
#
# Sobe o ecossistema completo em conjunto:
#   1. Backend HTTP BFF / Workflow Studio (Porta 8847)
#   2. Backend WebSocket Nexus / Agentes MCP (Porta 8848)
#   3. Frontend Nexus Vite (Porta 5173, conectado ao WebSocket)
#
# Uso: .\start-all.ps1
# Ou:  powershell -ExecutionPolicy Bypass -File .\start-all.ps1

param(
    [switch]$KillExisting = $false
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host ""
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "🧠 KIOSK BRANDS — SECOND BRAIN & NEXUS AGENT OFFICE" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# ── 1. Localizar Python ──────────────────────────────────────────────────
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    $Python = $VenvPython
    Write-Host "🐍 Usando Python do venv: .venv\Scripts\python.exe" -ForegroundColor Green
} else {
    $Python = "python"
    Write-Host "🐍 Usando Python global do sistema" -ForegroundColor Yellow
}

# ── 2. Função para verificar/liberar porta ─────────────────────────────────
function Ensure-PortFree([int]$Port, [string]$ServiceName) {
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($conn) {
        $pidNum = $conn.OwningProcess
        if ($KillExisting) {
            Write-Host "⚠️  Porta $Port ocupada pelo PID $pidNum. Encerrando processo..." -ForegroundColor Yellow
            Stop-Process -Id $pidNum -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 800
        } else {
            Write-Host "ℹ️  Porta $Port já está em uso por PID $pidNum ($ServiceName)." -ForegroundColor Cyan
        }
    }
}

Ensure-PortFree -Port 8847 -ServiceName "Dashboard HTTP"
Ensure-PortFree -Port 8848 -ServiceName "Nexus WebSocket"
Ensure-PortFree -Port 5173 -ServiceName "Nexus Vite"

# ── 3. Iniciar Backend 1: Dashboard HTTP / Workflow Studio (Porta 8847) ──
$conn8847 = Get-NetTCPConnection -LocalPort 8847 -ErrorAction SilentlyContinue
if (-not $conn8847) {
    Write-Host "▶  Iniciando Dashboard BFF HTTP na porta 8847..." -ForegroundColor Green
    $Job8847 = Start-Job -ScriptBlock {
        param($r, $py)
        Set-Location $r
        & $py dashboard/serve.py --port 8847
    } -ArgumentList $Root, $Python
    Start-Sleep -Seconds 1
} else {
    Write-Host "✅ Dashboard BFF HTTP já ativo na porta 8847" -ForegroundColor Green
}

# ── 4. Iniciar Backend 2: Nexus WebSocket Server (Porta 8848) ─────────────
$conn8848 = Get-NetTCPConnection -LocalPort 8848 -ErrorAction SilentlyContinue
if (-not $conn8848) {
    Write-Host "▶  Iniciando WebSocket Server em ws://127.0.0.1:8848..." -ForegroundColor Green
    $Job8848 = Start-Job -ScriptBlock {
        param($r, $py)
        Set-Location $r
        & $py -m backend.ws_server
    } -ArgumentList $Root, $Python
    Start-Sleep -Seconds 1
} else {
    Write-Host "✅ WebSocket Server já ativo na porta 8848" -ForegroundColor Green
}

# ── 5. Iniciar Frontend: Nexus Vite (Porta 5173) ──────────────────────────
$NexusDir = Join-Path $Root "nexus"
$NodeModules = Join-Path $NexusDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "📦 Instalando dependências do Nexus em $NexusDir..." -ForegroundColor Yellow
    Push-Location $NexusDir
    npm install
    Pop-Location
}

$env:VITE_ADAPTER_MODE = "ws"
$env:VITE_WS_URL = "ws://127.0.0.1:8848"

Write-Host ""
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "🚀 SERVIÇOS DO ECOSSISTEMA ATIVOS:" -ForegroundColor White
Write-Host "   📌 Second Brain Dashboard : http://127.0.0.1:8847" -ForegroundColor Cyan
Write-Host "   📌 Nexus Agent Workspace  : http://127.0.0.1:5173" -ForegroundColor Cyan
Write-Host "   📌 WebSocket Engine Python : ws://127.0.0.1:8848" -ForegroundColor Cyan
Write-Host "   📌 Auditoria de Execuções  : .runtime/workflow_audit.jsonl" -ForegroundColor Gray
Write-Host "----------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "   Pressione Ctrl+C para encerrar os servidores." -ForegroundColor DarkGray
Write-Host ""

try {
    Push-Location $NexusDir
    npm run dev
} finally {
    Write-Host ""
    Write-Host "🔴 Encerrando jobs de background..." -ForegroundColor Yellow
    if ($Job8847) { Stop-Job $Job8847 -ErrorAction SilentlyContinue; Remove-Job $Job8847 -ErrorAction SilentlyContinue }
    if ($Job8848) { Stop-Job $Job8848 -ErrorAction SilentlyContinue; Remove-Job $Job8848 -ErrorAction SilentlyContinue }
    Pop-Location
    Write-Host "✅ Finalizado." -ForegroundColor Green
}
