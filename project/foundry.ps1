param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$FoundryArgs
)

$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'orchestration\foundry.py'
if (-not (Test-Path $script)) { throw "Foundry orchestration CLI not found: $script" }

$python = Get-Command py -ErrorAction SilentlyContinue
if ($python) {
    & py -3 $script @FoundryArgs
} else {
    & python $script @FoundryArgs
}
exit $LASTEXITCODE
