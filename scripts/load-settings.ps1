param([string]$SettingsFile=(Join-Path $PSScriptRoot 'settings.json'))
$ErrorActionPreference='Stop'
try {
    . (Join-Path $PSScriptRoot 'config.ps1')
    Get-BaiduMcpSettings -SettingsFile $SettingsFile | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine('Cannot load Baidu MCP configuration. Check supported keys, quotes and paths; no configuration values are printed.')
    exit 1
}
