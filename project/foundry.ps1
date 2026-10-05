param(
  [Parameter(ValueFromRemainingArguments=$true)]
  [string[]]$Args
)
$tool = Join-Path $PSScriptRoot "Foundry\tools\foundry.py"
python $tool @Args
exit $LASTEXITCODE
