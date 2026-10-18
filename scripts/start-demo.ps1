param(
    [int]$DatabasePort = 6386,
    [int]$ApiPort = 8014,
    [int]$UiPort = 5183,
    [switch]$Agent
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
foreach ($port in @($ApiPort, $UiPort)) {
    if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
        throw "Port $port is already in use. Supply a different -ApiPort or -UiPort."
    }
}
$take = 'take_' + (Get-Date -Format 'MMddHHmmss')
$logs = Join-Path $repo "backend/eval/out/$take"
New-Item -ItemType Directory -Path $logs -Force | Out-Null
$env:FALKORDB_PORT = "$DatabasePort"
$env:ST_TEMPLATE = "st_facts_$take"
$env:ST_WORKSPACE = $take
$env:ST_SNAPSHOT = 'synthetic-v1'
$env:ST_MCP_URL = "http://127.0.0.1:$ApiPort/mcp/"
$env:PORT = "$ApiPort"
$env:LLM_PROVIDER = if ($Agent) { 'groq' } else { 'none' }
$env:JEV_ENABLED = 'false'
$apiProcess = Start-Process python -ArgumentList '-m','shelltrace' -WorkingDirectory (Join-Path $repo 'backend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'api.log') -RedirectStandardError (Join-Path $logs 'api.err')
$ready = $false
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$ApiPort/api/health" -TimeoutSec 2
        if ($health.status -eq 'ok') { $ready = $true; break }
    } catch { }
    Start-Sleep -Seconds 1
}
if (-not $ready) { throw "API failed to become ready. See $logs" }
$env:ST_UI_PORT = "$UiPort"
$env:ST_API_TARGET = "http://127.0.0.1:$ApiPort"
$webProcess = Start-Process npm.cmd -ArgumentList 'run','dev','--','--host','127.0.0.1' -WorkingDirectory (Join-Path $repo 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logs 'ui.log') -RedirectStandardError (Join-Path $logs 'ui.err')
Write-Output "Recording URL: http://127.0.0.1:$UiPort/?ws=$take"
Write-Output "Fresh synthetic template: st_facts_$take"
Write-Output "Model: $($health.llm). API PID: $($apiProcess.Id). UI launcher PID: $($webProcess.Id)."
Write-Output "Logs: $logs"
if ($Agent -and $health.llm -eq 'deterministic') { Write-Warning 'Groq credentials are missing. Use Playbook and describe it accurately.' }
