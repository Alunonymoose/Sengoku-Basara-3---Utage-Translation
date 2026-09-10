# Fix: battle dialogue / voice desync
#
# Cause: the 608 msg_m<stage>_pl<char>.arc files in rom\eng\id were rebuilt from
# Samurai Heroes' message tables. Those are indexed against SH's voice playlist
# (182 lines for Mount Osore / Ieyasu); Utage drives dialogue from its own
# playlist (343 lines for the same scene). Two different index spaces, so the
# text on screen never corresponds to the voice being played.
#
# This restores the stock tables from rom\jpn\id, which are indexed against
# Utage's own playlist. Battle dialogue returns to Japanese but name, portrait,
# text and voice agree again.
#
# Only rom\eng\id is touched. Nothing in rom\demo is affected, so every English
# stage title, character card and name plate stays as it is.
#
# The current files are backed up first - run UNDO_dialogue_desync.ps1 to revert.

$ErrorActionPreference = 'Stop'

$rom = 'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom'
$eng = Join-Path $rom 'eng\id'
$jpn = Join-Path $rom 'jpn\id'
$bak = Join-Path $rom 'eng\id_msg_BACKUP_pre_desync_fix'

foreach ($d in @($eng, $jpn)) {
    if (-not (Test-Path -LiteralPath $d)) { throw "Not found: $d" }
}

if (-not (Test-Path -LiteralPath $bak)) {
    New-Item -ItemType Directory -Path $bak | Out-Null
    Write-Host "Created backup folder: $bak"
} else {
    Write-Host "Backup folder already exists, leaving it as-is: $bak"
}

$targets = Get-ChildItem -LiteralPath $eng -Filter 'msg_m*_pl*.arc' -File

Write-Host ""
Write-Host ("Found {0} dialogue archives in rom\eng\id" -f $targets.Count)
Write-Host ""

$restored = 0
$skipped  = 0
$missing  = 0

foreach ($f in $targets) {
    $source = Join-Path $jpn $f.Name
    if (-not (Test-Path -LiteralPath $source)) {
        Write-Host ("  no stock original, left alone : {0}" -f $f.Name)
        $missing++
        continue
    }

    # already identical? then it was never patched - nothing to do
    $a = (Get-FileHash -LiteralPath $f.FullName -Algorithm MD5).Hash
    $b = (Get-FileHash -LiteralPath $source     -Algorithm MD5).Hash
    if ($a -eq $b) { $skipped++; continue }

    $backupPath = Join-Path $bak $f.Name
    if (-not (Test-Path -LiteralPath $backupPath)) {
        Copy-Item -LiteralPath $f.FullName -Destination $backupPath
    }
    Copy-Item -LiteralPath $source -Destination $f.FullName -Force
    $restored++
}

Write-Host ""
Write-Host "-------------------------------------------"
Write-Host ("  restored from stock : {0}" -f $restored)
Write-Host ("  already stock       : {0}" -f $skipped)
Write-Host ("  no original found   : {0}" -f $missing)
Write-Host "-------------------------------------------"
Write-Host ""
Write-Host "Done. Clear the RPCS3 game cache before testing:"
Write-Host "  right-click Sengoku BASARA 3 in the game list and remove its cache,"
Write-Host "  or delete dev_hdd1\caches\BLJM60389_BLJM60389"
Write-Host ""
Write-Host ("Originals of the replaced files are in: {0}" -f $bak)
