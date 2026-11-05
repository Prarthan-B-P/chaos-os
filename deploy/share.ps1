# Share CHAOS OS from this computer at a public HTTPS address, behind the login
# in deploy\secrets.yml. No server, account or card needed; it stays online
# while this computer is awake and Docker Desktop is running.
#   .\deploy\share.ps1          start sharing (prints the address)
#   .\deploy\share.ps1 -Stop    stop sharing and go back to the normal local lab
param([switch]$Stop)
$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
$files = @("-f", "docker-compose.yml", "-f", "deploy/docker-compose.prod.yml", "-f", "deploy/docker-compose.tunnel.yml")
$vars = "SITE_ADDRESS", "DASHBOARD_USER", "DASHBOARD_PASSWORD_HASH", "GRAFANA_PASSWORD", "PUBLIC_URL"

Push-Location $root
try {
    if ($Stop) {
        # The default files (with the local override) drop caddy and tunnel as orphans.
        docker compose up -d --wait --remove-orphans
        if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }
        Write-Host "Sharing stopped. Local dashboard: http://localhost:8090"
        return
    }

    if (-not (Test-Path "deploy\secrets.yml")) {
        throw "Create deploy\secrets.yml first: copy deploy\secrets.example.yml and fill it in."
    }
    $secrets = @{}
    foreach ($line in Get-Content "deploy\secrets.yml") {
        if ($line -match '^(\w+):\s*(.*?)\s*$') { $secrets[$Matches[1]] = $Matches[2].Trim('"', "'") }
    }
    foreach ($name in "dashboard_password", "grafana_password") {
        $value = [string]$secrets[$name]
        if ($value.Length -lt 12 -or $value -like "*change-me*") {
            throw "Set a long, real $name in deploy\secrets.yml (12+ characters)."
        }
    }

    $hash = docker run --rm caddy:2.8.4-alpine caddy hash-password --plaintext $secrets.dashboard_password
    if ($LASTEXITCODE -ne 0) { throw "Could not hash the password (is Docker Desktop running?)" }
    $env:SITE_ADDRESS = ":80"   # plain HTTP inside Docker; Cloudflare serves the HTTPS
    $env:DASHBOARD_USER = $secrets.dashboard_user
    $env:DASHBOARD_PASSWORD_HASH = $hash
    $env:GRAFANA_PASSWORD = $secrets.grafana_password

    # Start the tunnel first: Grafana needs the public address it will be served at.
    docker compose @files up -d tunnel
    if ($LASTEXITCODE -ne 0) { throw "Could not start the tunnel" }
    $url = $null
    for ($i = 0; $i -lt 30 -and -not $url; $i++) {
        $logs = docker compose @files logs tunnel | Out-String
        if ($logs -match 'https://[a-z0-9-]+\.trycloudflare\.com') { $url = $Matches[0] }
        else { Start-Sleep -Seconds 2 }
    }
    if (-not $url) { throw "No tunnel address yet; check: docker logs chaosos-tunnel-1" }
    $env:PUBLIC_URL = $url

    Write-Host "Starting the lab behind $url (the first run builds images)..."
    docker compose @files up -d --build --wait --remove-orphans
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }

    # A new address takes a moment to reach Cloudflare's DNS.
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $auth = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes("$($secrets.dashboard_user):$($secrets.dashboard_password)"))
    $live = $false
    for ($i = 0; $i -lt 30 -and -not $live; $i++) {
        try {
            $r = Invoke-WebRequest "$url/api/overview" -Headers @{ Authorization = "Basic $auth" } -UseBasicParsing -TimeoutSec 10
            $live = $r.StatusCode -eq 200
        } catch { Start-Sleep -Seconds 3 }
    }
    if (-not $live) { Write-Warning "The address is not answering yet; give it a minute and refresh." }

    Write-Host ""
    Write-Host "CHAOS OS is shared at $url" -ForegroundColor Green
    Write-Host "  Log in as '$($secrets.dashboard_user)' with the password in deploy\secrets.yml"
    Write-Host "  Grafana: $url/grafana"
    Write-Host "  Online while this computer is awake. Stop: .\deploy\share.ps1 -Stop"
    Start-Process $url   # open the public link in the browser
}
finally {
    foreach ($name in $vars) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
    Pop-Location
}
