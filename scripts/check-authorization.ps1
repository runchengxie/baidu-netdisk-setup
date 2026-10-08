param([string]$TokenFile, [switch]$Online)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'read-credential.ps1') -TokenFile $TokenFile -Mode status -Online:$Online
