param(
    [Parameter(Mandatory=$true)][string]$TaskName,
    [Parameter(Mandatory=$true)][string]$LiveRoot,
    [string]$Agent = 'agent',
    [string]$BaseBranch = 'foundry-v0.2-orchestration',
    [string]$WorktreeRoot
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$foundry = Join-Path $repo 'project\foundry.ps1'
if (-not $WorktreeRoot) {
    $WorktreeRoot = Join-Path (Split-Path $repo -Parent) '.basara-worktrees'
}
New-Item -ItemType Directory -Path $WorktreeRoot -Force | Out-Null

$state = Join-Path $LiveRoot '.foundry'
$current = Join-Path $state 'CURRENT_SNAPSHOT'
if (-not (Test-Path $current)) {
    & $foundry snapshot $LiveRoot
    if ($LASTEXITCODE -ne 0) { throw "Failed to create live snapshot." }
}
& $foundry verify $LiveRoot
if ($LASTEXITCODE -ne 0) { throw "Live tree changed since CURRENT_SNAPSHOT; create a fresh snapshot before agent handoff." }

$snapshotId = (Get-Content $current -Raw).Trim()
if ($snapshotId.Length -ne 64) { throw "Invalid snapshot id: $snapshotId" }

$slug = ($TaskName.ToLowerInvariant() -replace '[^a-z0-9]+','-').Trim('-')
if (-not $slug) { throw 'TaskName produced an empty slug.' }
$agentSlug = ($Agent.ToLowerInvariant() -replace '[^a-z0-9]+','-').Trim('-')
$short = $snapshotId.Substring(0,12)
$branch = "agent/$agentSlug/$slug-$short"
$dir = Join-Path $WorktreeRoot "$agentSlug-$slug-$short"

Push-Location $repo
try {
    git fetch origin
    if ($LASTEXITCODE -ne 0) { throw 'git fetch failed' }
    git worktree add -b $branch $dir $BaseBranch
    if ($LASTEXITCODE -ne 0) { throw 'git worktree add failed' }
}
finally { Pop-Location }

$contract = [ordered]@{
    schema = 'BASARA_FOUNDRY_AGENT_TASK_V1'
    task = $TaskName
    agent = $Agent
    source_snapshot_id = $snapshotId
    source_live_root = (Resolve-Path $LiveRoot).Path
    base_branch = $BaseBranch
    branch = $branch
    created_utc = [DateTimeOffset]::UtcNow.ToString('o')
    rules = @(
        'Do not mutate the live game tree directly.',
        'Current-build claims must come from the bound snapshot/query/runtime evidence.',
        'Before producing patch outputs, verify that the live tree still matches the bound snapshot.',
        'Artwork approval is candidate-SHA-bound; changed art requires new approval.',
        'Commit code/recipes/evidence metadata only; never commit copyrighted game assets.'
    )
}
$contractPath = Join-Path $dir 'AGENT_TASK.local.json'
$contract | ConvertTo-Json -Depth 6 | Set-Content -Path $contractPath -Encoding utf8

Write-Host "Worktree: $dir"
Write-Host "Branch:   $branch"
Write-Host "Snapshot: $snapshotId"
Write-Host "Contract: $contractPath"
