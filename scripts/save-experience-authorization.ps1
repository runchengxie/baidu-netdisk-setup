param([string]$TokenFile)
$ErrorActionPreference = 'Stop'
if (-not $TokenFile) { $TokenFile = Join-Path $PSScriptRoot 'experience-token.json' }
$inputSecure = Read-Host 'Paste the complete official login_success URL here (hidden input; do not send it to chat)' -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($inputSecure)
try { $text = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) }
finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) }
$temporary = $null
try {
    $uri = [Uri]$text
    if ($uri.Scheme -ne 'https' -or $uri.Host -ne 'openapi.baidu.com' -or $uri.AbsolutePath -ne '/oauth/2.0/login_success') { throw 'Unexpected URL' }
    $values = @{}
    foreach ($pair in $uri.Fragment.TrimStart('#').Split('&')) {
        $parts = $pair.Split('=', 2)
        if ($parts.Count -eq 2) { $values[[Uri]::UnescapeDataString($parts[0])] = [Uri]::UnescapeDataString($parts[1]) }
    }
    if (-not $values.access_token -or [long]$values.expires_in -le 0) { throw 'Missing token or lifetime' }
    $secure = ConvertTo-SecureString $values.access_token -AsPlainText -Force
    $TokenFile = [IO.Path]::GetFullPath($TokenFile)
    $directory = Split-Path -Parent $TokenFile
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary = Join-Path $directory ([Guid]::NewGuid().ToString() + '.tmp')
    [ordered]@{ access_token=(ConvertFrom-SecureString $secure); expires_in=[long]$values.expires_in; scope=$values.scope; client_id='QHOuRXiepJBMjtk0esLhrPoNlQyYd0mF'; saved_at_utc=[DateTime]::UtcNow.ToString('o'); purpose='Official MCP experience authorization' } | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls $temporary /inheritance:r /grant:r "$($identity):(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot restrict credential permissions' }
    Move-Item -LiteralPath $temporary -Destination $TokenFile -Force
    $temporary = $null
    Write-Host 'Saved Windows-user-encrypted authorization. Restart both MCP connections to use it.'
} catch {
    Write-Error 'Authorization was not saved. Use the complete official login_success URL in the hidden prompt; do not share the URL or token.'
} finally {
    if ($temporary -and (Test-Path -LiteralPath $temporary)) { Remove-Item -LiteralPath $temporary }
    $text=$null; $values=$null; $secure=$null; $inputSecure=$null
}
