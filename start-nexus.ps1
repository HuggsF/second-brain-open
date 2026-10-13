# start-nexus.ps1 — Inicia o Nexus Agent Office (WebSocket backend + frontend Vite)
#
# Uso: .\start-nexus.ps1
# Opcional: .\start-nexus.ps1 -AdapterMode local   (para rodar só a simulação, sem backend)
#
# Portas:
#   8847 — Dashboard Second Brain (serve.py, já deve estar rodando)
#   8848 — WebSocket backend do Nexus (ws_server.py)
#   5173 — Frontend Vite do Nexus (npm run dev)

param(
    [string]$AdapterMode = "ws"
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot

Write-Host ""
Write-Host "🏢 Nexus Agent Office — Iniciando..." -ForegroundColor Cyan
Write-Host ""

# ── Verificar venv ─────────────────────────────────────────────────────────
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "❌ venv não encontrado em .venv\Scripts\python.exe" -ForegroundColor Red
    Write-Host "   Execute: python -m venv .venv && .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# ── Verificar node ─────────────────────────────────────────────────────────
$NexusDir = Join-Path $Root "nexus"
$NodeModules = Join-Path $NexusDir "node_modules"
if (-not (Test-Path $NodeModules)) {
    Write-Host "📦 node_modules ausente — instalando dependências do Nexus..." -ForegroundColor Yellow
    Push-Location $NexusDir
    npm install
    Pop-Location
}

# ── Modo local: só Vite ────────────────────────────────────────────────────
if ($AdapterMode -eq "local") {
    Write-Host "▶  Modo LOCAL — simulação sem backend Python" -ForegroundColor Yellow
    $env:VITE_ADAPTER_MODE = "local"
    Push-Location $NexusDir
    npm run dev
    exit 0
}

# ── Modo ws: WebSocket backend + Vite ─────────────────────────────────────
Write-Host "1/2 Iniciando WebSocket backend em ws://127.0.0.1:8848 ..." -ForegroundColor Green
$WsJob = Start-Job -ScriptBlock {
    param($root, $py)
    Set-Location $root
    & $py -m backend.ws_server
} -ArgumentList $Root, $Python

Start-Sleep -Seconds 2

# Verificar se o backend subiu
$wsRunning = $false
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("127.0.0.1", 8848)
    $tcp.Close()
    $wsRunning = $true
    Write-Host "   ✅ WebSocket backend OK (porta 8848)" -ForegroundColor Green
} catch {
    Write-Host "   ⚠️  Backend ainda iniciando — aguarde alguns segundos após o Vite abrir" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "2/2 Iniciando Nexus Vite em http://127.0.0.1:5173 ..." -ForegroundColor Green
Write-Host ""
Write-Host "──────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  Dashboard  → http://127.0.0.1:8847  (Second Brain)" -ForegroundColor White
Write-Host "  Nexus      → http://127.0.0.1:5173  (Vite direto)" -ForegroundColor White
Write-Host "  WebSocket  → ws://127.0.0.1:8848    (backend Python)" -ForegroundColor White
Write-Host "  Nexus na nav do dashboard → #page=nexus" -ForegroundColor White
Write-Host "──────────────────────────────────────────────" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Ctrl+C para encerrar ambos os servidores" -ForegroundColor DarkGray
Write-Host ""

try {
    Push-Location $NexusDir
    npm run dev
} finally {
    Write-Host ""
    Write-Host "🔴 Encerrando WebSocket backend..." -ForegroundColor Red
    Stop-Job $WsJob -ErrorAction SilentlyContinue
    Remove-Job $WsJob -ErrorAction SilentlyContinue
    Pop-Location
}
