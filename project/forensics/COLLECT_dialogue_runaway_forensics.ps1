# Sengoku BASARA 3 Utage - dialogue runaway forensic collector
# Read-only against the game tree. Copies evidence into a timestamped folder.

$ErrorActionPreference = 'Stop'

$Root = 'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3'
$GameRoot = Split-Path $Root -Parent
$Stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$Out = Join-Path (Get-Location) ("UTAGE_DIALOGUE_FORENSICS_$Stamp")
New-Item -ItemType Directory -Force -Path $Out | Out-Null

function Add-FileEvidence {
    param([string]$Path, [string]$Label)
    $destDir = Join-Path $Out 'files'
    New-Item -ItemType Directory -Force -Path $destDir | Out-Null
    if (Test-Path -LiteralPath $Path) {
        $f = Get-Item -LiteralPath $Path
        $sha256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLower()
        $sha1 = (Get-FileHash -LiteralPath $Path -Algorithm SHA1).Hash.ToLower()
        [pscustomobject]@{
            label = $Label
            path = $Path
            exists = $true
            size = $f.Length
            modified_utc = $f.LastWriteTimeUtc.ToString('o')
            sha256 = $sha256
            sha1 = $sha1
        } | ConvertTo-Json -Depth 4 | Set-Content -Encoding UTF8 (Join-Path $destDir ($Label + '.json'))
        Copy-Item -LiteralPath $Path -Destination (Join-Path $destDir ($Label + [IO.Path]::GetExtension($Path))) -Force
    } else {
        [pscustomobject]@{ label=$Label; path=$Path; exists=$false } |
            ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $destDir ($Label + '.json'))
    }
}

if (-not (Test-Path -LiteralPath $Root)) { throw "Game nativePS3 root not found: $Root" }

# Executable currently booted by RPCS3.
Add-FileEvidence -Path (Join-Path $GameRoot 'EBOOT.BIN') -Label 'LOCAL_EBOOT_BIN'

# The outer-route providers that the current RPCS3 log proved were being opened from rom/jpn.
foreach ($lang in @('jpn','eng')) {
    Add-FileEvidence -Path (Join-Path $Root "rom\$lang\startup.arc") -Label ("${lang}_startup")
    Add-FileEvidence -Path (Join-Path $Root "rom\$lang\basara.arc") -Label ("${lang}_basara")
    Add-FileEvidence -Path (Join-Path $Root "rom\$lang\id\cockpit1P.arc") -Label ("${lang}_cockpit1P")
    Add-FileEvidence -Path (Join-Path $Root "rom\$lang\id\cockpit2P.arc") -Label ("${lang}_cockpit2P")
}

# Representative dialogue pairs: one SH-overlap stage and one Utage-only stage.
$targets = @(
    @{ stage='m034'; player='pl013' },
    @{ stage='m045'; player='pl013' }
)
foreach ($t in $targets) {
    foreach ($lang in @('jpn','eng')) {
        $idName = "msg_$($t.stage)_$($t.player).arc"
        $msgName = "$($t.stage)_$($t.player).arc"
        Add-FileEvidence -Path (Join-Path $Root "rom\$lang\id\$idName") -Label ("${lang}_id_$idName")
        Add-FileEvidence -Path (Join-Path $Root "rom\$lang\msg\$msgName") -Label ("${lang}_msg_$msgName")
    }
}

# Build a concise inventory of all mission dialogue archives in both namespaces.
$inventory = @()
foreach ($lang in @('jpn','eng')) {
    foreach ($sub in @('id','msg')) {
        $dir = Join-Path $Root "rom\$lang\$sub"
        if (Test-Path -LiteralPath $dir) {
            $pattern = if ($sub -eq 'id') { 'msg_m*_pl*.arc' } else { 'm*_pl*.arc' }
            Get-ChildItem -LiteralPath $dir -Filter $pattern -File | ForEach-Object {
                $inventory += [pscustomobject]@{
                    lang = $lang
                    domain = $sub
                    name = $_.Name
                    size = $_.Length
                    modified_utc = $_.LastWriteTimeUtc.ToString('o')
                    sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLower()
                }
            }
        }
    }
}
$inventory | Sort-Object lang,domain,name | Export-Csv -NoTypeInformation -Encoding UTF8 (Join-Path $Out 'dialogue_inventory.csv')

# Include the newest RPCS3 log if discoverable under the user's RPCS3 folders.
$logCandidates = @()
$roots = @(
    "$env:USERPROFILE\Downloads",
    "$env:APPDATA\RPCS3",
    "$env:LOCALAPPDATA\RPCS3"
)
foreach ($r in $roots) {
    if (Test-Path -LiteralPath $r) {
        $logCandidates += Get-ChildItem -LiteralPath $r -Filter 'RPCS3.log' -File -Recurse -ErrorAction SilentlyContinue
    }
}
$newestLog = $logCandidates | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
if ($newestLog) {
    Copy-Item -LiteralPath $newestLog.FullName -Destination (Join-Path $Out 'RPCS3.log') -Force
    [pscustomobject]@{ path=$newestLog.FullName; modified_utc=$newestLog.LastWriteTimeUtc.ToString('o'); size=$newestLog.Length } |
        ConvertTo-Json | Set-Content -Encoding UTF8 (Join-Path $Out 'RPCS3_log_source.json')
}

# Record the already-proven reference fingerprints so the result can be reconciled without guesswork.
[pscustomobject]@{
    known_drive_upn_elf_sha256 = 'a3cafcb5656a0d6ec7bdf9f2a273cb494e3e195950dd06b2c1d19ff97a43b99b'
    known_drive_upn_elf_sha1 = 'd41878311602b1357e7828f002dff3fd94d81cf3'
    known_stock_elf_sha256 = 'b1d23e53cbf33dd43ea04d6c57d4df651b0f3785496166c88b39ff68f89f69c9'
    known_stock_elf_sha1 = 'fd7d716cd3c0f00237573d0c995b000484e1ca4b'
    observed_rpcs3_ppu_hash = 'PPU-e03e70a536e4e3693ebe5d6b729d6cc5fce411d1'
    observed_runtime = @(
        'rom/jpn/startup.arc',
        'rom/jpn/basara.arc',
        'rom/jpn/id/cockpit1P.arc',
        'rom/jpn/id/cockpit2P.arc'
    )
} | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 (Join-Path $Out 'known_reference_fingerprints.json')

$zip = "$Out.zip"
Compress-Archive -Path (Join-Path $Out '*') -DestinationPath $zip -Force
Write-Host ""
Write-Host "Forensic pack created:"
Write-Host "  $zip"
Write-Host ""
Write-Host "No game files were modified."
