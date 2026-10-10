param([string]$SettingsFile=(Join-Path $PSScriptRoot 'settings.json'), [switch]$Force)
$ErrorActionPreference='Stop'
try {
    . (Join-Path $PSScriptRoot 'refresh.ps1')
    $settings=Get-BaiduMcpSettings -SettingsFile $SettingsFile
    Invoke-BaiduEnsureAuthorization -Settings $settings -Force:$Force | ConvertTo-Json -Compress
} catch {
    [Console]::Error.WriteLine('Cannot check or refresh Baidu authorization; no credential-bearing diagnostic is printed.')
    exit 1
}
