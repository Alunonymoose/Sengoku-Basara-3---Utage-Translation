param(
    [string]$PamfTool = ".\PAMFtool-Utage-win-x64.exe",
    [string]$Original = "E:\Utage Patching New\PS3_GAME\USRDIR\nativePS3\movie\op029_00.pam",
    [string]$WorkRoot = "E:\BASARA_AUDITS\PAM_IDENTITY"
)

$ErrorActionPreference = 'Stop'

$ExpectedSha = 'f815aa4ffcf157af7c25690804eae73d243d199f68a4ecdc21fab21ce67fb364'
$ExpectedSize = 120393728
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$Verifier = Join-Path $Here 'pam_identity_verify.py'

if (-not (Test-Path -LiteralPath $PamfTool -PathType Leaf)) {
    throw "Patched PAMFtool not found: $PamfTool"
}
if (-not (Test-Path -LiteralPath $Original -PathType Leaf)) {
    throw "Pilot PAM not found: $Original"
}
if (-not (Test-Path -LiteralPath $Verifier -PathType Leaf)) {
    throw "Verifier not found: $Verifier"
}

$fi = Get-Item -LiteralPath $Original
$sha = (Get-FileHash -LiteralPath $Original -Algorithm SHA256).Hash.ToLowerInvariant()
if ($fi.Length -ne $ExpectedSize -or $sha -ne $ExpectedSha) {
    throw @"
REFUSING OP029 IDENTITY PILOT: current source is not the pinned fixture.
Expected size: $ExpectedSize
Actual size:   $($fi.Length)
Expected SHA:  $ExpectedSha
Actual SHA:    $sha

Do not overwrite or remux a newer/different live file using the old fixture parameters.
Generate a fresh source profile first.
"@
}

$help = & $PamfTool -h 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { throw "PAMFtool -h failed." }
if ($help -notmatch '-m2v-pstd' -or $help -notmatch '-header-start-pts') {
    throw "Wrong PAMFtool build: Utage identity-preservation options are missing."
}

$stamp = Get-Date -Format 'yyyy-MM-dd_HHmmss'
$work = Join-Path $WorkRoot "op029_00_$stamp"
$origDemux = Join-Path $work 'original_demux'
$remuxDemux = Join-Path $work 'remux_demux'
$remux = Join-Path $work 'op029_00.identity-remux.pam'
$verify = Join-Path $work 'PAM_IDENTITY_VERIFY.json'
$rootReady = Join-Path $work 'ROOT_READY_TEST_ONLY\PS3_GAME\USRDIR\nativePS3\movie'
New-Item -ItemType Directory -Path $origDemux,$remuxDemux,$rootReady -Force | Out-Null

@{
    generated_local = (Get-Date).ToString('o')
    original = (Resolve-Path -LiteralPath $Original).Path
    original_sha256 = $sha
    original_size = $fi.Length
    pamftool = (Resolve-Path -LiteralPath $PamfTool).Path
    fixture = 'project/media_tools/fixtures/op029_00.identity.json'
    intended_args = @(
        '-m2v-pstd','1234',
        '-initial-scr','30',
        '-header-start-pts','89310',
        '-muxrate','48000',
        '-std-delay','90000'
    )
} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $work 'PILOT_CONTEXT.json') -Encoding UTF8

Write-Host "1/5 PAMF info..."
& $PamfTool -info $Original 2>&1 |
    Tee-Object -FilePath (Join-Path $work 'ORIGINAL_INFO.txt')
if ($LASTEXITCODE -ne 0) { throw "PAMFtool info failed." }

Write-Host "2/5 Demux exact source..."
& $PamfTool -demux $Original $origDemux 2>&1 |
    Tee-Object -FilePath (Join-Path $work 'ORIGINAL_DEMUX.log')
if ($LASTEXITCODE -ne 0) { throw "Original demux failed." }

Write-Host "3/5 Identity remux with source-preserving contract..."
$muxArgs = @(
    '-mux', $origDemux, $remux,
    '-m2v-pstd', '1234',
    '-initial-scr', '30',
    '-header-start-pts', '89310',
    '-muxrate', '48000',
    '-std-delay', '90000'
)
& $PamfTool @muxArgs 2>&1 |
    Tee-Object -FilePath (Join-Path $work 'REMUX.log')
if ($LASTEXITCODE -ne 0) { throw "Identity remux failed." }

Write-Host "4/5 Re-demux candidate..."
& $PamfTool -demux $remux $remuxDemux 2>&1 |
    Tee-Object -FilePath (Join-Path $work 'REMUX_DEMUX.log')
if ($LASTEXITCODE -ne 0) { throw "Candidate re-demux failed." }

Write-Host "5/5 Structural verification..."
$verifyArgs = @(
    $Verifier,
    '--original', $Original,
    '--remux', $remux,
    '--original-demux', $origDemux,
    '--remux-demux', $remuxDemux,
    '--out', $verify
)
& python @verifyArgs
$verifyCode = $LASTEXITCODE
if ($verifyCode -ne 0) {
    throw "Identity verifier failed. See $verify"
}

$candidateSha = (Get-FileHash -LiteralPath $remux -Algorithm SHA256).Hash.ToLowerInvariant()
Copy-Item -LiteralPath $remux -Destination (Join-Path $rootReady 'op029_00.pam') -Force

$instructions = @"
OP029_00 IDENTITY REMUX — RUNTIME TEST ONLY

STRUCTURAL VERIFIER: PASS
Original SHA-256: $ExpectedSha
Candidate SHA-256: $candidateSha

This is NOT an English-subtitled movie yet.
It is the decoder/container identity gate.

Before runtime test:
1. Keep the real current E: original recoverable.
2. Verify it still hashes to $ExpectedSha.
3. Copy only the test candidate from:
   $rootReady
4. Cold-boot RPCS3.
5. Trigger the exact scene that loads op029_00.pam.

PASS requires:
- scene starts normally;
- video plays start-to-finish;
- 5.1 ATRAC3plus audio plays;
- A/V sync is normal;
- no decoder hang/stutter attributable to the remux;
- scene returns to the game normally.

After test, restore original unless the runtime result is intentionally being kept.
Bind screenshot/log evidence to candidate SHA-256:
$candidateSha

Verifier:
$verify
"@
$instructions | Set-Content -LiteralPath (Join-Path $work 'RUNTIME_TEST.txt') -Encoding UTF8

Write-Host ""
Write-Host "STRUCTURAL PASS."
Write-Host "Work folder:    $work"
Write-Host "Candidate SHA:  $candidateSha"
Write-Host "Runtime bundle: $(Join-Path $work 'ROOT_READY_TEST_ONLY')"
Write-Host "Test notes:     $(Join-Path $work 'RUNTIME_TEST.txt')"
Write-Host ""
Write-Host "Do not call the PAM mux path runtime-proven until the cold-boot scene test passes."
