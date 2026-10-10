param([string]$AppKey, [string]$SecretFile, [string]$SettingsFile=(Join-Path $PSScriptRoot 'settings.json'))
$ErrorActionPreference='Stop'
try {
    . (Join-Path $PSScriptRoot 'config.ps1')
    $settings=Get-BaiduMcpSettings -SettingsFile $SettingsFile
    if (-not $AppKey) { $AppKey=$settings.appKey }
    if (-not $AppKey) { $AppKey=Read-Host 'Enter the AppKey belonging to this authorization' }
    if (-not $SecretFile) { $SecretFile=$settings.secretFile }
    $secret=Read-Host 'Enter the corresponding application SecretKey (hidden input)' -AsSecureString
    try { Save-BaiduAppSecret -AppKey $AppKey -Secret $secret -SecretFile $SecretFile }
    finally { $secret.Dispose() }
    Write-Host 'Saved a Windows-user-encrypted SecretKey. Restart both MCPs to use automatic refresh when matching refresh credentials are available.'
} catch {
    [Console]::Error.WriteLine('SecretKey was not saved. Check the AppKey, destination and file permissions; an existing file must belong to the same application.')
    exit 1
}
