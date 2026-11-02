# Deploy (or update) CHAOS OS on your server.
#   .\deploy\deploy.ps1 -Server 129.1.2.3
#   .\deploy\deploy.ps1 -Server 129.1.2.3 -User ubuntu -Key $HOME\.ssh\id_ed25519
param(
    [Parameter(Mandatory = $true)][string]$Server,
    [string]$User = "ubuntu",
    [string]$Key = "$HOME\.ssh\id_ed25519"
)
$ErrorActionPreference = "Stop"
$deployDir = $PSScriptRoot

if (-not (Test-Path "$deployDir\secrets.yml")) {
    throw "Create deploy\secrets.yml first: copy deploy\secrets.example.yml and fill it in."
}
if (-not (Test-Path $Key)) { throw "SSH private key not found: $Key" }

docker build -q -t chaosos-deployer "$deployDir\runner" | Out-Null
docker run --rm -it `
    -v "${Key}:/keys/id:ro" `
    -v "${deployDir}:/deploy" `
    chaosos-deployer -i "$Server," -u $User deploy.yml
