function Assert-BaiduPrivatePath {
    param([string]$Path)
    $cursor=Split-Path -Parent ([IO.Path]::GetFullPath($Path))
    # A home-level dotfiles repository can contain ignored private configuration
    # and temporary directories. It is not a project source boundary.
    $profileRoot=[Environment]::GetFolderPath('UserProfile').TrimEnd('\','/')
    while ($cursor) {
        if ((Test-Path -LiteralPath (Join-Path $cursor '.git')) -and $cursor.TrimEnd('\','/') -ne $profileRoot) { throw 'Private configuration must be outside source repositories' }
        $parent=[IO.Directory]::GetParent($cursor)
        if (-not $parent) { break }
        $cursor=$parent.FullName
    }
}

function Get-BaiduMcpSettings {
    param([Parameter(Mandatory)][string]$SettingsFile, [string]$EnvFile)
    $settings = @{}
    if (Test-Path -LiteralPath $SettingsFile) {
        $saved = Get-Content -Raw -LiteralPath $SettingsFile | ConvertFrom-Json
        foreach ($property in $saved.PSObject.Properties) { $settings[$property.Name] = $property.Value }
    }
    $directory = Split-Path -Parent ([IO.Path]::GetFullPath($SettingsFile))
    if (-not $EnvFile) { $EnvFile = $env:BAIDU_MCP_ENV_FILE }
    if (-not $EnvFile) { $EnvFile = $settings.envFile }
    if (-not $EnvFile) { $EnvFile = Join-Path $directory '.env' }
    if (-not [IO.Path]::IsPathRooted($EnvFile)) { $EnvFile = Join-Path $directory $EnvFile }
    $EnvFile = [IO.Path]::GetFullPath($EnvFile)
    $values = @{}
    $mapping = @{ BAIDU_MCP_TOKEN_FILE='tokenFile'; BAIDU_MCP_APP_KEY='appKey'; BAIDU_MCP_SECRET_FILE='secretFile' }
    if (Test-Path -LiteralPath $EnvFile) {
        $lineNumber = 0
        foreach ($line in (Get-Content -LiteralPath $EnvFile -Encoding utf8)) {
            $lineNumber++
            $text = $line.Trim()
            if (-not $text -or $text.StartsWith('#')) { continue }
            if ($text -notmatch '^([A-Z][A-Z0-9_]*)\s*=\s*(.*)$') { throw "Invalid env configuration at line $lineNumber" }
            $name=$Matches[1]; $value=$Matches[2].Trim()
            if (-not $mapping.ContainsKey($name) -or $values.ContainsKey($name)) { throw "Unsupported or duplicate env setting at line $lineNumber" }
            if ($value.StartsWith('"') -or $value.StartsWith("'")) {
                if ($value.Length -lt 2 -or $value[-1] -ne $value[0]) { throw "Unclosed quoted env value at line $lineNumber" }
                $value = $value.Substring(1,$value.Length-2)
            }
            $values[$name]=$value
        }
    }
    foreach ($name in $mapping.Keys) {
        $value=[Environment]::GetEnvironmentVariable($name,'Process')
        if (-not $value) { $value=$values[$name] }
        if ($value) { $settings[$mapping[$name]]=$value }
    }
    $settings.envFile=$EnvFile
    if (-not $settings.secretFile) { $settings.secretFile=Join-Path $directory 'app-secret.json' }
    foreach ($key in @('tokenFile','secretFile')) {
        if ($settings[$key]) {
            if (-not [IO.Path]::IsPathRooted($settings[$key])) { $settings[$key]=Join-Path (Split-Path -Parent $EnvFile) $settings[$key] }
            $settings[$key]=[IO.Path]::GetFullPath($settings[$key])
        }
    }
    if (-not $settings.appKey -and (Test-Path -LiteralPath $settings.secretFile)) {
        try {
            $secret=Get-Content -Raw -LiteralPath $settings.secretFile | ConvertFrom-Json
            if ($secret.format -eq 'baidu-mcp-secret-v1') { $settings.appKey=[string]$secret.app_key }
        } catch { } # Credential status will explain unreadable files without leaking values.
    }
    return $settings
}

function Get-BaiduRefreshStatus {
    param([hashtable]$Settings, [bool]$HasRefreshToken)
    $reason='ready'; $decryptable=$false
    if (-not $HasRefreshToken) { $reason='missing_refresh_token' }
    elseif (-not $Settings.appKey) { $reason='missing_app_key' }
    elseif (-not (Test-Path -LiteralPath $Settings.secretFile)) { $reason='missing_secret_file' }
    else {
        try {
            $saved=Get-Content -Raw -LiteralPath $Settings.secretFile | ConvertFrom-Json
            if ($saved.format -ne 'baidu-mcp-secret-v1' -or $saved.app_key -ne $Settings.appKey) { $reason='app_key_mismatch' }
            else {
                $secure=ConvertTo-SecureString ([string]$saved.secret_key)
                try { $decryptable=($secure.Length -gt 0) } finally { $secure.Dispose() }
                if (-not $decryptable) { $reason='secret_unreadable' }
            }
        } catch { $reason='secret_unreadable' }
    }
    return @{ refreshMaterialsReady=($reason -eq 'ready'); refreshConfigurationStatus=$reason; secretDecryptable=$decryptable; automaticRefresh=($reason -eq 'ready') }
}

function Save-BaiduAppSecret {
    param([Parameter(Mandatory)][string]$AppKey, [Parameter(Mandatory)][Security.SecureString]$Secret, [Parameter(Mandatory)][string]$SecretFile)
    if ($AppKey -notmatch '^[A-Za-z0-9_-]+$' -or $Secret.Length -eq 0) { throw 'AppKey or SecretKey is empty or invalid' }
    $SecretFile=[IO.Path]::GetFullPath($SecretFile)
    Assert-BaiduPrivatePath -Path $SecretFile
    if (Test-Path -LiteralPath $SecretFile) {
        $old=Get-Content -Raw -LiteralPath $SecretFile | ConvertFrom-Json
        if ($old.format -ne 'baidu-mcp-secret-v1' -or $old.app_key -ne $AppKey) { throw 'Existing secret file belongs to another application; select a different file' }
    }
    $directory=Split-Path -Parent $SecretFile
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
    $temporary=Join-Path $directory ([Guid]::NewGuid().ToString()+'.tmp')
    try {
        [ordered]@{format='baidu-mcp-secret-v1';app_key=$AppKey;secret_key=(ConvertFrom-SecureString $Secret);saved_at_utc=[DateTime]::UtcNow.ToString('o')} | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
        $identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
        & icacls $temporary /inheritance:r /grant:r "$($identity):(F)" | Out-Null
        if ($LASTEXITCODE -ne 0) { throw 'Cannot restrict secret permissions' }
        Move-Item -LiteralPath $temporary -Destination $SecretFile -Force
    } finally { if (Test-Path -LiteralPath $temporary) { Remove-Item -LiteralPath $temporary } }
}
