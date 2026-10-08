param([string]$TokenFile, [switch]$Online)
$ErrorActionPreference = 'Stop'
if (-not $TokenFile) { $settings = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'settings.json') | ConvertFrom-Json; $TokenFile = $settings.tokenFile }
& (Join-Path $PSScriptRoot 'read-credential.ps1') -TokenFile $TokenFile -Mode status -Online:$Online
