param(
    [string]$LiveRoot = 'E:\Utage Patching New',
    [string]$SamuraiHeroesRoot = 'E:\SAMURAI HEROES',
    [string[]]$Rpcs3Log = @(),
    [string]$AuditRoot = 'E:\BASARA_AUDITS',
    [switch]$LikelyTextTextureReview
)

$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$AuditTool = Join-Path $Here 'foundry_release_audit.py'
$TextureReview = Join-Path $Here 'texture_review_export.py'

if (-not (Test-Path -LiteralPath $LiveRoot -PathType Container)) {
    throw "Live root not found: $LiveRoot"
}
if (-not (Test-Path -LiteralPath $SamuraiHeroesRoot -PathType Container)) {
    throw "Samurai Heroes root not found: $SamuraiHeroesRoot"
}

$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$out = Join-Path $AuditRoot $stamp
New-Item -ItemType Directory -Path $out -Force | Out-Null

$args = @(
    $AuditTool,
    $LiveRoot,
    '--sh-root', $SamuraiHeroesRoot,
    '--out', $out
)
foreach ($log in $Rpcs3Log) {
    if (-not (Test-Path -LiteralPath $log -PathType Leaf)) {
        throw "RPCS3 log not found: $log"
    }
    $args += @('--rpcs3-log', $log)
}

Write-Host "Running BASARA release audit..."
& python @args
$code = $LASTEXITCODE
if ($code -notin 0,1) {
    throw "Release audit infrastructure failed with exit code $code"
}

$reviewOut = Join-Path $out 'texture_review'
$reviewArgs = @($TextureReview, $LiveRoot, '--out', $reviewOut)
if ($LikelyTextTextureReview) {
    $reviewArgs += '--likely-text-only'
}
Write-Host "Exporting deduplicated texture review..."
& python @reviewArgs
$reviewCode = $LASTEXITCODE
if ($reviewCode -notin 0,1) {
    throw "Texture review exporter failed with exit code $reviewCode"
}

Write-Host ""
Write-Host "Audit complete (engineering status may intentionally be non-pass)."
Write-Host "Audit folder: $out"
Write-Host "Summary:      $(Join-Path $out 'AUDIT_SUMMARY.md')"
Write-Host "Unresolved:   $(Join-Path $out 'UNRESOLVED.json')"
Write-Host "Texture HTML: $(Join-Path $reviewOut 'index.html')"
Write-Host "Runtime test: $(Join-Path $out 'RUNTIME_ACCEPTANCE_MATRIX.json')"

exit $code
