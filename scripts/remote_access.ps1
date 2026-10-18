param(
    [ValidateSet('Start', 'Stop', 'Status')]
    [string]$Action = 'Status'
)

$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$remoteDirectory = Join-Path $taskRoot 'infrastructure/remote-access'
$remoteEnv = Join-Path $remoteDirectory '.env'
$remoteCompose = Join-Path $remoteDirectory 'docker-compose.yml'
if (-not (Test-Path -LiteralPath $remoteEnv)) {
    throw 'Run python scripts/setup_remote_access.py first to create local login credentials.'
}
$composeArgs = @('compose', '--env-file', $remoteEnv, '-f', $remoteCompose)

function Get-RemoteUrl {
    $tunnelLog = & docker @composeArgs logs --no-color --tail 100 remote-tunnel 2>&1 | Out-String
    $urlMatches = [regex]::Matches($tunnelLog, 'https://[a-z0-9-]+\.trycloudflare\.com')
    if ($urlMatches.Count -gt 0) { return $urlMatches[$urlMatches.Count - 1].Value }
    return $null
}

if ($Action -eq 'Stop') {
    & docker @composeArgs stop remote-tunnel remote-access
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the remote entry.' }
    Write-Output 'Remote access stopped. Local services and data are unchanged.'
    exit 0
}
if ($Action -eq 'Start') {
    & docker @composeArgs up -d --build --wait remote-access
    if ($LASTEXITCODE -ne 0) { throw 'Protected entry did not start. Tunnel was not started.' }
    & docker @composeArgs up -d --no-deps remote-tunnel
    if ($LASTEXITCODE -ne 0) { throw 'Could not start the tunnel.' }
    for ($attempt = 0; $attempt -lt 15; $attempt++) {
        if (Get-RemoteUrl) { break }
        Start-Sleep -Seconds 2
    }
}
& docker @composeArgs ps
$remoteUrl = Get-RemoteUrl
if ($remoteUrl) {
    @{ url = $remoteUrl; observedAt = (Get-Date).ToUniversalTime().ToString('o'); temporary = $true } |
        ConvertTo-Json | Set-Content -LiteralPath (Join-Path $remoteDirectory '.connection.json') -Encoding UTF8
    Write-Output "Remote URL: $remoteUrl"
    Write-Output "Login details: $(Join-Path $remoteDirectory '.credentials.json')"
} else {
    Write-Output 'No tunnel URL found yet. Check remote-tunnel logs; no usable external URL is confirmed.'
}
