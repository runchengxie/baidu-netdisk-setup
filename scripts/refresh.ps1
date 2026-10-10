# Shared by both launchers. Credentials never leave this process except in the
# official HTTPS form body and Windows-user-encrypted files.
. (Join-Path $PSScriptRoot 'config.ps1')

function Get-BaiduExpiry {
    param($Saved, [DateTimeOffset]$Now=[DateTimeOffset]::UtcNow)
    try {
        if ([long]$Saved.expires_in -le 0 -or -not $Saved.saved_at_utc) { throw 'Invalid lifetime' }
        $created=if ($Saved.saved_at_utc -is [DateTime]) { [DateTimeOffset]::new($Saved.saved_at_utc) } else { [DateTimeOffset]::Parse([string]$Saved.saved_at_utc) }
        $expires=$created.AddSeconds([long]$Saved.expires_in)
        $remaining=($expires-$Now).TotalSeconds
        return @{status=$(if ($remaining -le 0) {'expired'} elseif ($remaining -le 604800) {'expiring'} else {'valid'});expiresAtUtc=$expires.UtcDateTime.ToString('o');remainingSeconds=$remaining;revision=$created.UtcDateTime.ToString('o')}
    } catch { return @{status='unknown';remainingSeconds=0;revision='unknown'} }
}

function Request-BaiduRefresh {
    param([Collections.Generic.Dictionary[string,string]]$Fields)
    Add-Type -AssemblyName System.Net.Http
    $handler=[Net.Http.HttpClientHandler]::new()
    $handler.UseProxy=$false; $handler.AllowAutoRedirect=$false
    $client=[Net.Http.HttpClient]::new($handler)
    $client.Timeout=[TimeSpan]::FromSeconds(30)
    $form=[Net.Http.FormUrlEncodedContent]::new($Fields)
    try {
        $response=$client.PostAsync('https://openapi.baidu.com/oauth/2.0/token',$form).GetAwaiter().GetResult()
        try {
            $data=$response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
            if (-not $response.IsSuccessStatusCode -and -not $data.error) { throw 'HTTP rejection' }
            return $data
        } finally { $response.Dispose() }
    } finally { $form.Dispose(); $client.Dispose() }
}

function Save-BaiduRefreshedAuthorization {
    param([string]$TokenFile, $Response, [DateTimeOffset]$Now)
    Assert-BaiduPrivatePath -Path $TokenFile
    $access=ConvertTo-SecureString ([string]$Response.access_token) -AsPlainText -Force
    $refresh=ConvertTo-SecureString ([string]$Response.refresh_token) -AsPlainText -Force
    try {
        $data=[ordered]@{access_token=(ConvertFrom-SecureString $access);refresh_token=(ConvertFrom-SecureString $refresh);expires_in=[long]$Response.expires_in;saved_at_utc=$Now.ToString('o')}
    } finally { $access.Dispose(); $refresh.Dispose() }
    $temporary=$TokenFile+'.pending-refresh.json'
    $data | ConvertTo-Json | Set-Content -LiteralPath $temporary -Encoding utf8
    $identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name
    & icacls $temporary /inheritance:r /grant:r "$($identity):(F)" | Out-Null
    if ($LASTEXITCODE -ne 0) { Remove-Item -LiteralPath $temporary; throw 'Cannot restrict permissions' }
    # File.Move with overwrite is an atomic same-volume rename on this Windows
    # runtime. Retain the encrypted pending file if the final replacement fails:
    # the server may already have rotated its refresh token.
    [IO.File]::Move($temporary,$TokenFile,$true)
}

function Invoke-BaiduEnsureAuthorization {
    param([hashtable]$Settings, [switch]$Force, [scriptblock]$Request={param($fields) Request-BaiduRefresh -Fields $fields})
    Assert-BaiduPrivatePath -Path $Settings.tokenFile
    $saved=Get-Content -Raw -LiteralPath $Settings.tokenFile | ConvertFrom-Json
    $result=Get-BaiduExpiry -Saved $saved
    $initialRevision=$result.revision
    $result.refreshAction='not_due'
    if (-not $Force -and $result.remainingSeconds -gt 604800) { return $result }
    $materials=Get-BaiduRefreshStatus -Settings $Settings -HasRefreshToken ([bool]$saved.refresh_token)
    if (-not $materials.refreshMaterialsReady) {
        $result.refreshAction='unavailable'; $result.refreshFailure=$materials.refreshConfigurationStatus
        return $result
    }
    $lock=$null; $deadline=[DateTimeOffset]::UtcNow.AddSeconds(45)
    try {
        while (-not $lock) {
            try { $lock=[IO.File]::Open(($Settings.tokenFile+'.refresh.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None) }
            catch [IO.IOException] {
                if ([DateTimeOffset]::UtcNow -ge $deadline) { throw 'Lock timeout' }
                Start-Sleep -Milliseconds 100
            }
        }
        # Re-read under the lock. A second launcher uses the first one's result.
        $saved=Get-Content -Raw -LiteralPath $Settings.tokenFile | ConvertFrom-Json
        $result=Get-BaiduExpiry -Saved $saved
        $result.refreshAction='not_due'
        if ($result.revision -ne $initialRevision -or (-not $Force -and $result.remainingSeconds -gt 604800)) { return $result }
        if (Test-Path -LiteralPath ($Settings.tokenFile+'.pending-refresh.json')) {
            $result.refreshAction='failed'; $result.refreshFailure='pending_credentials_recovery_required'
            return $result
        }
        $fields=[Collections.Generic.Dictionary[string,string]]::new()
        $fields.Add('grant_type','refresh_token'); $fields.Add('client_id',$Settings.appKey)
        $secret=Get-Content -Raw -LiteralPath $Settings.secretFile | ConvertFrom-Json
        if ($secret.app_key -ne $Settings.appKey) { throw 'Application changed' }
        foreach ($entry in @(@('refresh_token',[string]$saved.refresh_token),@('client_secret',[string]$secret.secret_key))) {
            $secure=ConvertTo-SecureString $entry[1]
            $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
            try { $fields.Add($entry[0],[Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)) }
            finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer); $secure.Dispose() }
        }
        $response=& $Request $fields
        if ($response.error) {
            $result.refreshAction='failed'
            $result.refreshFailure=if ([string]$response.error -in @('invalid_grant','expired_token')) {'reauthorization_required'} elseif ([string]$response.error -eq 'invalid_client') {'app_credentials_rejected'} else {'oauth_rejected'}
            return $result
        }
        if (-not $response.access_token -or -not $response.refresh_token -or [long]$response.expires_in -le 0 -or [long]$response.expires_in -gt 31536000) { throw 'Invalid response' }
        try { Save-BaiduRefreshedAuthorization -TokenFile $Settings.tokenFile -Response $response -Now ([DateTimeOffset]::UtcNow) }
        catch { $result.refreshAction='failed'; $result.refreshFailure='credential_save_failed'; return $result }
        $saved=Get-Content -Raw -LiteralPath $Settings.tokenFile | ConvertFrom-Json
        $result=Get-BaiduExpiry -Saved $saved; $result.refreshAction='refreshed'
        return $result
    } catch {
        $result.refreshAction='failed'; $result.refreshFailure='network_or_local_failure'
        return $result
    } finally {
        if ($lock) { $lock.Dispose() }
        if ($fields) { $fields.Clear() }
        $response=$null
    }
}
