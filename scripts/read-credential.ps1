param([Parameter(Mandatory)][string]$TokenFile, [ValidateSet('token', 'status')][string]$Mode = 'status', [switch]$Online)
$ErrorActionPreference = 'Stop'
try {
    $saved = Get-Content -Raw -LiteralPath $TokenFile | ConvertFrom-Json
    $state = 'unknown'
    $expires = $null
    if ($saved.saved_at_utc -and [long]$saved.expires_in -gt 0) {
        # Recent PowerShell versions deserialize ISO strings as DateTime. Preserve
        # its Kind instead of converting to a culture-dependent, zone-less string.
        $created = if ($saved.saved_at_utc -is [DateTime]) { [DateTimeOffset]::new($saved.saved_at_utc) } else { [DateTimeOffset]::Parse([string]$saved.saved_at_utc) }
        $expires = $created.AddSeconds([long]$saved.expires_in)
        $remaining = ($expires - [DateTimeOffset]::UtcNow).TotalSeconds
        $state = if ($remaining -le 0) { 'expired' } elseif ($remaining -le 604800) { 'expiring' } else { 'valid' }
    }
    if ($Mode -eq 'token' -and $state -eq 'expired') { throw 'Expired authorization' }
    $secure = ConvertTo-SecureString ([string]$saved.access_token)
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $token = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
        if (-not $token) { throw 'Empty credential' }
        if ($Mode -eq 'token') {
            if ($state -eq 'expiring') { [Console]::Error.WriteLine('Baidu authorization expires within 7 days. Reauthorize soon.') }
            [Console]::Out.Write($token)
        } else {
            $result = [ordered]@{ status = $state; expiresAtUtc = $(if ($expires) { $expires.UtcDateTime.ToString('o') } else { $null }); hasRefreshToken = [bool]$saved.refresh_token; automaticRefresh = $false; decryptable = $true }
            if ($Online) {
                $query = 'https://pan.baidu.com/rest/2.0/xpan/nas?method=uinfo&access_token=' + [Uri]::EscapeDataString($token)
                try { $response = Invoke-RestMethod -Uri $query -TimeoutSec 25; $result.onlineErrno = $response.errno; $result.onlineValid = ($response.errno -eq 0) }
                catch { $result.onlineValid = $false; $result.onlineFailure = 'Request failed. No credential-bearing diagnostic is printed.' }
            }
            $result | ConvertTo-Json -Compress
        }
    } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr); $token = $null; $query = $null }
} catch {
    [Console]::Error.WriteLine('Cannot read a usable Windows-encrypted Baidu authorization. Check the file, Windows account and expiry; run the authorization script again.')
    exit 1
}
