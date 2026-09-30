param(
    [Parameter(Mandatory=$true)]
    [string]$GameRoot,

    [string]$Manifest = (Join-Path $PSScriptRoot "manifest.json")
)

$ErrorActionPreference = "Stop"

function Get-SHA256([string]$Path) {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    exit 1
}

$GameRoot = (Resolve-Path -LiteralPath $GameRoot).Path
$Ps3Game = if (Test-Path -LiteralPath (Join-Path $GameRoot "PS3_GAME")) {
    Join-Path $GameRoot "PS3_GAME"
} elseif ((Split-Path -Leaf $GameRoot) -ieq "PS3_GAME") {
    $GameRoot
} else {
    Fail "Could not find PS3_GAME under: $GameRoot"
}

if (-not (Test-Path -LiteralPath $Manifest)) {
    Fail "Patch manifest not found: $Manifest"
}

$manifestData = Get-Content -LiteralPath $Manifest -Raw | ConvertFrom-Json

if ($manifestData.title_id -ne "BLJM60389") {
    Fail "Manifest is not for BLJM60389."
}

$patchRoot = Split-Path -Parent (Resolve-Path -LiteralPath $Manifest).Path
$backupRoot = Join-Path $Ps3Game ("_UTAGE_EN_BACKUP_" + (Get-Date -Format "yyyyMMdd-HHmmss"))

Write-Host "Sengoku BASARA 3 Utage English Patch"
Write-Host "Target: $Ps3Game"
Write-Host "Manifest version: $($manifestData.patch_version)"
Write-Host ""

# First pass: verify every source before changing anything.
foreach ($entry in $manifestData.files) {
    $target = Join-Path $Ps3Game $entry.path
    if (-not (Test-Path -LiteralPath $target)) {
        Fail "Required file is missing: $($entry.path)"
    }

    $actual = Get-SHA256 $target
    $expected = $entry.base_sha256.ToLowerInvariant()

    if ($actual -ne $expected) {
        Fail "Unsupported or already-modified file: $($entry.path)
Expected: $expected
Found:    $actual"
    }

    Write-Host "[OK] verified $($entry.path)"
}

Write-Host ""
Write-Host "All source files match. Beginning patch transaction..."

foreach ($entry in $manifestData.files) {
    $target = Join-Path $Ps3Game $entry.path
    $backup = Join-Path $backupRoot $entry.path
    $backupDir = Split-Path -Parent $backup
    New-Item -ItemType Directory -Force -Path $backupDir | Out-Null
    Copy-Item -LiteralPath $target -Destination $backup -Force

    if ($entry.type -eq "xdelta3") {
        $patchFile = Join-Path $patchRoot $entry.patch
        if (-not (Test-Path -LiteralPath $patchFile)) {
            Fail "Patch payload missing: $($entry.patch)"
        }

        $xdelta = Get-Command xdelta3 -ErrorAction SilentlyContinue
        if (-not $xdelta) {
            $localXdelta = Join-Path $patchRoot "tools\xdelta3.exe"
            if (Test-Path -LiteralPath $localXdelta) {
                $xdeltaExe = $localXdelta
            } else {
                Fail "xdelta3 was not found. Put xdelta3.exe in the patch package's tools folder or add it to PATH."
            }
        } else {
            $xdeltaExe = $xdelta.Source
        }

        $temp = "$target.utagepatch.tmp"
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }

        & $xdeltaExe -d -s $target $patchFile $temp
        if ($LASTEXITCODE -ne 0) {
            Fail "xdelta3 failed for $($entry.path)"
        }

        Move-Item -LiteralPath $temp -Destination $target -Force
    }
    else {
        Fail "Unsupported patch type '$($entry.type)' for $($entry.path)"
    }

    $result = Get-SHA256 $target
    $expectedResult = $entry.result_sha256.ToLowerInvariant()

    if ($result -ne $expectedResult) {
        Copy-Item -LiteralPath $backup -Destination $target -Force
        Fail "Post-patch verification failed for $($entry.path). Original file restored."
    }

    Write-Host "[OK] patched $($entry.path)"
}

Write-Host ""
Write-Host "Patch installed successfully." -ForegroundColor Green
Write-Host "Backups: $backupRoot"
