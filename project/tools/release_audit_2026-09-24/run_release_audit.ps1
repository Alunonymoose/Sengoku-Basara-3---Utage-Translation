param(
    [string]$LiveRoot = 'E:\Utage Patching New',
    [string]$SamuraiHeroesRoot = 'E:\SAMURAI HEROES',
    [string[]]$Rpcs3Log = @(),
    [string]$AuditRoot = 'E:\BASARA_AUDITS',
    [switch]$LikelyTextTextureReview,
    [switch]$NoPreviousDiff
)

$ErrorActionPreference = 'Stop'

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$AuditTool = Join-Path $Here 'foundry_release_audit.py'
$TextureReview = Join-Path $Here 'texture_review_export.py'
$CompareAudits = Join-Path $Here 'compare_audits.py'

if (-not (Test-Path -LiteralPath $LiveRoot -PathType Container)) {
    throw "Live root not found: $LiveRoot"
}
if (-not (Test-Path -LiteralPath $SamuraiHeroesRoot -PathType Container)) {
    throw "Samurai Heroes root not found: $SamuraiHeroesRoot"
}

New-Item -ItemType Directory -Path $AuditRoot -Force | Out-Null

$previous = $null
if (-not $NoPreviousDiff) {
    $previous = Get-ChildItem -LiteralPath $AuditRoot -Directory -ErrorAction SilentlyContinue |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName '00_RUN_METADATA.json') -PathType Leaf } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$out = Join-Path $AuditRoot $stamp
New-Item -ItemType Directory -Path $out -Force | Out-Null

# Bind the audit artifact to the exact Git checkout when this launcher is run
# from a repository clone. Failure to resolve git is recorded, not fatal.
$repoRoot = Resolve-Path (Join-Path $Here '..\..\..') -ErrorAction SilentlyContinue
$gitHead = $null
if ($repoRoot) {
    try {
        $gitHead = (& git -C $repoRoot.Path rev-parse HEAD 2>$null).Trim()
        if ($LASTEXITCODE -ne 0 -or -not $gitHead) { $gitHead = $null }
    } catch {
        $gitHead = $null
    }
}
@{
    generated_local = (Get-Date).ToString('o')
    repo_head = $gitHead
    live_root = (Resolve-Path -LiteralPath $LiveRoot).Path
    samurai_heroes_root = (Resolve-Path -LiteralPath $SamuraiHeroesRoot).Path
    previous_audit = if ($previous) { $previous.FullName } else { $null }
} | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $out 'LAUNCH_CONTEXT.json') -Encoding UTF8

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

$diffOut = $null
if ($previous -and -not $NoPreviousDiff) {
    $diffOut = Join-Path $out 'diff_from_previous'
    Write-Host "Comparing against previous audit: $($previous.FullName)"
    & python $CompareAudits $previous.FullName $out --out $diffOut
    if ($LASTEXITCODE -ne 0) {
        throw "Audit diff failed with exit code $LASTEXITCODE"
    }
}

# Recompute a launcher-level digest after review/diff generation. This is not
# the live-tree digest; it is an integrity fingerprint for the audit artifact.
$artifactHashes = @{}
Get-ChildItem -LiteralPath $out -File -Recurse |
    Where-Object { $_.Name -ne 'AUDIT_ARTIFACT_SHA256.json' } |
    Sort-Object FullName |
    ForEach-Object {
        $rel = $_.FullName.Substring($out.Length).TrimStart('\','/').Replace('\','/')
        $artifactHashes[$rel] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
$artifactHashes | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (Join-Path $out 'AUDIT_ARTIFACT_SHA256.json') -Encoding UTF8

Write-Host ""
Write-Host "Audit complete (engineering status may intentionally be non-pass)."
Write-Host "Audit folder: $out"
Write-Host "Summary:      $(Join-Path $out 'AUDIT_SUMMARY.md')"
Write-Host "Unresolved:   $(Join-Path $out 'UNRESOLVED.json')"
Write-Host "Textures:     $(Join-Path $reviewOut 'index.html')"
Write-Host "Runtime test: $(Join-Path $out 'RUNTIME_ACCEPTANCE_MATRIX.json')"
Write-Host "Launch bind:  $(Join-Path $out 'LAUNCH_CONTEXT.json')"
if ($diffOut) {
    Write-Host "Delta:        $(Join-Path $diffOut 'AUDIT_DIFF.md')"
}
Write-Host ""
if ($code -eq 0) {
    Write-Host "Audit release gate: PASS"
} else {
    Write-Host "Audit release gate: OPEN/BLOCKED rows remain (expected during engineering)."
}

exit $code
