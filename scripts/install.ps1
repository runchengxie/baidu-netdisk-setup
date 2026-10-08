param(
    [string]$WorkspaceConfig = (Join-Path $env:USERPROFILE '.config/runchengxie/shared/workspace.toml'),
    [string]$DataRoot,
    [string]$ConfigRoot,
    [string]$TokenFile,
    [switch]$SkipDependencies
)
$ErrorActionPreference = 'Stop'
# Accept this workspace's three simple root keys; no general TOML parsing is implied.
if (Test-Path -LiteralPath $WorkspaceConfig) {
    $text = Get-Content -Raw -LiteralPath $WorkspaceConfig
    if (-not $DataRoot -and $text -match '(?m)^data_root\s*=\s*"([^"]+)"\s*$') { $DataRoot = $Matches[1] }
    if (-not $ConfigRoot -and $text -match '(?m)^config_root\s*=\s*"([^"]+)"\s*$') { $ConfigRoot = $Matches[1] }
}
if (-not $DataRoot -or -not $ConfigRoot) { throw 'Supply -DataRoot and -ConfigRoot, or a workspace TOML containing both roots.' }
$DataRoot = [IO.Path]::GetFullPath($DataRoot)
$ConfigRoot = [IO.Path]::GetFullPath($ConfigRoot)
$data = Join-Path $DataRoot 'baidu-netdisk-mcp'
$deployment = Join-Path $ConfigRoot 'deployments/baidu-netdisk-mcp'
$runtime = Join-Path $data 'runtime'
$official = Join-Path $runtime 'official-mcp'
$officialDir = Join-Path $official 'src/baidu-netdisk'
$revision = 'b3983d330fea79c7b72e6b7014803e1830148d2c'
$node = (Get-Command node -ErrorAction Stop).Source
$powershell = (Get-Command pwsh -ErrorAction Stop).Source
$codex = (Get-Command codex -ErrorAction Stop).Source
New-Item -ItemType Directory -Force -Path $deployment,$runtime | Out-Null
$settingsPath = Join-Path $deployment 'settings.json'
if (-not $TokenFile -and (Test-Path -LiteralPath $settingsPath)) { $TokenFile = (Get-Content -Raw -LiteralPath $settingsPath | ConvertFrom-Json).tokenFile }
if (-not $TokenFile) { $TokenFile = Join-Path $deployment 'experience-token.json' }
$TokenFile = [IO.Path]::GetFullPath($TokenFile)
if (-not $SkipDependencies) {
    $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
    & $npm install --prefix $runtime --save-exact 'mcp-remote@0.14.3'
    if ($LASTEXITCODE -ne 0) { throw 'Bridge installation failed' }
    if (-not (Test-Path -LiteralPath $official)) {
        git clone https://github.com/baidu-netdisk/mcp.git $official
        if ($LASTEXITCODE -ne 0) { throw 'Official checkout failed' }
        git -C $official checkout --detach $revision
        if ($LASTEXITCODE -ne 0) { throw 'Cannot select the pinned official revision' }
    }
    uv sync --frozen --python 3.12 --project $officialDir
    if ($LASTEXITCODE -ne 0) { throw 'Official Python environment installation failed' }
}
$head = git -C $official rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or $head -ne $revision) { throw 'The official checkout does not match the pinned revision. Existing checkout was preserved.' }
$python = Join-Path $officialDir '.venv/Scripts/python.exe'
$bridge = Join-Path $runtime 'node_modules/mcp-remote/dist/proxy.js'
if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $bridge)) { throw 'Runtime dependencies are missing' }
foreach ($name in @('policy.py','read-credential.ps1','check-authorization.ps1','save-experience-authorization.ps1','start-remote.mjs','start-local.py','check-mcp.py')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination (Join-Path $deployment $name)
}
[ordered]@{ tokenFile=$TokenFile; powershell=$powershell; bridge=$bridge; officialDir=$officialDir; dataRoot=$DataRoot; configRoot=$ConfigRoot } | ConvertTo-Json | Set-Content -LiteralPath $settingsPath -Encoding utf8
& $codex mcp add baidu-netdisk -- $node (Join-Path $deployment 'start-remote.mjs')
if ($LASTEXITCODE -ne 0) { throw 'Remote MCP registration failed' }
& $codex mcp add baidu-netdisk-local-uploader -- $python (Join-Path $deployment 'start-local.py')
if ($LASTEXITCODE -ne 0) { throw 'Local MCP registration failed' }
Write-Host 'Registered remote and local-upload MCPs. Save authorization if needed, run check-authorization.ps1 -Online, then restart Codex.'
