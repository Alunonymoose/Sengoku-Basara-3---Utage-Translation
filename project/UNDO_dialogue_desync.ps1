# Undo for FIX_dialogue_desync.ps1
#
# Puts the previous rom\eng\id dialogue archives back exactly as they were,
# from the backup folder the fix script created. Use this if you want the
# English battle text returned (desync and all), or before attempting the
# proper re-index rebuild.

$ErrorActionPreference = 'Stop'

$rom = 'E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\rom'
$eng = Join-Path $rom 'eng\id'
$bak = Join-Path $rom 'eng\id_msg_BACKUP_pre_desync_fix'

if (-not (Test-Path -LiteralPath $bak)) { throw "No backup folder found at: $bak" }

$files = Get-ChildItem -LiteralPath $bak -Filter 'msg_m*_pl*.arc' -File
Write-Host ("Restoring {0} files to rom\eng\id" -f $files.Count)

$n = 0
foreach ($f in $files) {
    Copy-Item -LiteralPath $f.FullName -Destination (Join-Path $eng $f.Name) -Force
    $n++
}

Write-Host ""
Write-Host ("Restored {0} files." -f $n)
Write-Host "Clear the RPCS3 game cache before testing."
